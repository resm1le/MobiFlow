from __future__ import annotations

from typing import Protocol

from mobiflow_agent.agents.contracts import AgentRole, ReplanDecisionType, StepDecisionType
from mobiflow_agent.common.contracts import EntityKind, VerificationStatus, VerificationVerdict
from mobiflow_agent.platform.types import GovernedActionState
from mobiflow_agent.runtime.state import ConfirmationState
from mobiflow_agent.task.completion import TaskCompletionVerdict
from mobiflow_agent.task.plan import TaskStatus, TaskStepKind
from mobiflow_agent.task.session import TaskSession

from .state import TaskGraphState


TERMINAL_STATUSES = {
    TaskStatus.COMPLETED,
    TaskStatus.FAILED,
    TaskStatus.AWAITING_APPROVAL,
    TaskStatus.HANDED_OFF,
}


class TaskGraphOps(Protocol):
    def _initialize_plan(self, session: TaskSession) -> None: ...
    def _activate_step(self, session: TaskSession, step_index: int) -> None: ...
    def _transition(self, session: TaskSession, status: TaskStatus) -> None: ...
    def _build_request(self, session: TaskSession, role: AgentRole, reason: str): ...
    def _record_result(self, session: TaskSession, result, *, next_role: AgentRole | None) -> None: ...
    def _refresh_session_context(self, session: TaskSession) -> None: ...
    def _complete_step(self, session: TaskSession) -> None: ...
    def _next_role_after_success(self, session: TaskSession) -> AgentRole | None: ...
    def _set_execution_state(self, session: TaskSession, execution_result, caller_context) -> None: ...
    def _clear_pending_execution(self, session: TaskSession) -> None: ...
    def _execution_failure_verdict(self, session: TaskSession, execution_result): ...
    def _approval_rejection_verdict(self, session: TaskSession, *, expired: bool): ...
    def _map_completion(self, status: VerificationStatus) -> TaskCompletionVerdict: ...
    def _refresh_support_context(self, session: TaskSession, *, capability: str) -> None: ...
    def _refresh_memory_runtime_context(self, session: TaskSession, *, role: AgentRole, storage_key: str) -> None: ...
    def _writeback_memory(self, session: TaskSession) -> None: ...
    def _set_active_model_profile(self, session: TaskSession, role: AgentRole | None) -> None: ...
    def _build_recovery_observation(self, session: TaskSession, recovery_outcome): ...
    def _complete_step_without_verification(self, session: TaskSession) -> None: ...

    @property
    def _dispatcher(self): ...

    @property
    def _policy(self): ...


def ensure_plan(state: TaskGraphState, ops: TaskGraphOps) -> dict:
    session = state.session
    if session.status == TaskStatus.AWAITING_APPROVAL and (
        state.resume_decision is not None or state.resume_expired
    ):
        return {"route_hint": "resume_approval", "last_error": None}
    if session.status in TERMINAL_STATUSES:
        return {"route_hint": "finalize", "last_error": None}
    if session.plan is None:
        ops._initialize_plan(session)
    else:
        ops._activate_step(session, session.current_step_index)
    return {"session": session, "route_hint": _active_step_route(session), "last_error": None}


def activate_step(state: TaskGraphState, ops: TaskGraphOps) -> dict:
    session = state.session
    if session.status in TERMINAL_STATUSES:
        return {"route_hint": "finalize"}
    if session.current_step is None:
        ops._transition(session, TaskStatus.COMPLETED)
        session.completion_verdict = TaskCompletionVerdict.TASK_COMPLETED
        return {"session": session, "route_hint": "finalize"}
    ops._activate_step(session, session.current_step_index)
    return {"session": session, "route_hint": _active_step_route(session)}


def dynamic_observe(state: TaskGraphState, ops: TaskGraphOps) -> dict:
    session = state.session
    ops._transition(session, TaskStatus.OBSERVING)
    observer_request = ops._build_request(
        session,
        AgentRole.OBSERVER,
        "Read the latest platform facts for the active dynamic task step.",
    )
    try:
        observation, observer_result = ops._dispatcher.observer.observe(session, observer_request)
        session.last_observation = observation
        ops._record_result(session, observer_result, next_role=AgentRole.STEP_POLICY)
        ops._refresh_session_context(session)
        return {"session": session, "route_hint": "decide_step", "last_error": None}
    except Exception as exc:  # pragma: no cover
        session.recovery_state = str(exc)
        ops._refresh_session_context(session)
        return {"session": session, "route_hint": "recover", "last_error": str(exc)}


def decide_step(state: TaskGraphState, ops: TaskGraphOps) -> dict:
    session = state.session
    if session.current_step is None or session.current_step.policy is None:
        return {"session": session, "route_hint": "recover", "last_error": "Dynamic step requires policy."}
    step_id = session.current_step.step_id
    iteration = session.step_policy_iterations.get(step_id, 0) + 1
    session.step_policy_iterations[step_id] = iteration
    if iteration > session.current_step.policy.max_iterations:
        session.last_verdict = _dynamic_blocked_verdict(
            session,
            blocked_reason="step_policy_max_iterations_exceeded",
            summary=f"Dynamic step policy exceeded max_iterations={session.current_step.policy.max_iterations}.",
        )
        ops._refresh_session_context(session)
        return {"session": session, "route_hint": "recover", "last_error": "max_iterations_exceeded"}

    ops._set_active_model_profile(session, AgentRole.STEP_POLICY)
    decision_request = ops._build_request(
        session,
        AgentRole.STEP_POLICY,
        "Choose the next bounded action for the active dynamic task step.",
    )
    decision, decision_result = ops._dispatcher.step_policy.decide(session, decision_request)
    session.last_step_decision = decision
    session.step_decisions.append(decision)

    if decision.decision_type == StepDecisionType.OBSERVE_AGAIN:
        next_role = AgentRole.OBSERVER
        route_hint = "dynamic_observe"
    elif decision.decision_type == StepDecisionType.PROPOSE_EXECUTION:
        if decision.proposal is None or decision.proposal.action_tool_name not in session.current_step.allowed_side_effects:
            session.last_verdict = _dynamic_blocked_verdict(
                session,
                blocked_reason="disallowed_dynamic_proposal",
                summary="Dynamic step policy proposed a side effect outside the active step allowlist.",
            )
            next_role = AgentRole.RECOVERY
            route_hint = "recover"
        else:
            next_role = AgentRole.EXECUTOR
            route_hint = "dynamic_execute"
    elif decision.decision_type == StepDecisionType.STEP_SUCCEEDED:
        next_role = AgentRole.VERIFIER
        route_hint = "verify"
    elif decision.decision_type in {StepDecisionType.STEP_BLOCKED, StepDecisionType.REQUEST_REPLAN}:
        session.last_verdict = _dynamic_blocked_verdict(
            session,
            blocked_reason=decision.blocked_reason or decision.decision_type.value,
            summary=decision.summary,
        )
        next_role = AgentRole.RECOVERY
        route_hint = "recover"
    elif decision.decision_type == StepDecisionType.HANDOFF:
        ops._transition(session, TaskStatus.HANDED_OFF)
        session.completion_verdict = TaskCompletionVerdict.BLOCKED
        session.recovery_state = decision.summary
        next_role = None
        route_hint = "finalize"
    else:  # pragma: no cover
        next_role = AgentRole.RECOVERY
        route_hint = "recover"

    ops._record_result(session, decision_result, next_role=next_role)
    ops._refresh_session_context(session)
    return {"session": session, "route_hint": route_hint, "last_error": None}


def dynamic_execute(state: TaskGraphState, ops: TaskGraphOps) -> dict:
    session = state.session
    if ops._dispatcher.executor is None:
        raise ValueError("TaskGraphRuntime requires an ExecutorAgent for executable dynamic steps.")
    ops._transition(session, TaskStatus.EXECUTING)
    executor_request = ops._build_request(
        session,
        AgentRole.EXECUTOR,
        "Submit the dynamic step policy governed side-effect proposal.",
    )
    execution_result, caller_context, executor_result = ops._dispatcher.executor.execute(session, executor_request)
    ops._set_execution_state(session, execution_result, caller_context)
    if execution_result.state == GovernedActionState.APPROVAL_REQUIRED:
        ops._record_result(session, executor_result, next_role=None)
        ops._transition(session, TaskStatus.AWAITING_APPROVAL)
        session.completion_verdict = TaskCompletionVerdict.BLOCKED
        ops._refresh_session_context(session)
        return {"session": session, "route_hint": "finalize", "last_error": None}

    ops._clear_pending_execution(session)
    ops._record_result(session, executor_result, next_role=AgentRole.OBSERVER)
    if execution_result.state != GovernedActionState.EXECUTED:
        session.last_verdict = ops._execution_failure_verdict(session, execution_result)
        ops._refresh_session_context(session)
        return {"session": session, "route_hint": "recover", "last_error": None}

    ops._refresh_session_context(session)
    return {"session": session, "route_hint": "dynamic_observe", "last_error": None}


def resume_approval(state: TaskGraphState, ops: TaskGraphOps) -> dict:
    session = state.session
    if session.status != TaskStatus.AWAITING_APPROVAL:
        raise ValueError("TaskGraphRuntime.resume requires a session awaiting approval.")
    if session.pending_execution is None:
        raise ValueError("TaskGraphRuntime.resume requires pending execution on the session.")
    if state.resume_decision is None and not state.resume_expired:
        raise ValueError("resume() requires approved=True/False or expired=True.")

    if state.resume_expired or state.resume_decision is False:
        session.pending_execution = session.pending_execution.model_copy(
            update={
                "confirmation_state": (
                    ConfirmationState.EXPIRED if state.resume_expired else ConfirmationState.REJECTED
                ),
            }
        )
        failure_verdict = ops._approval_rejection_verdict(session, expired=state.resume_expired)
        session.pending_execution = None
        session.last_verdict = failure_verdict
        return {"session": session, "route_hint": "recover", "last_error": None}

    if ops._dispatcher.executor is None:
        raise ValueError("TaskGraphRuntime.resume requires an ExecutorAgent.")
    ops._transition(session, TaskStatus.EXECUTING)
    executor_request = ops._build_request(
        session,
        AgentRole.EXECUTOR,
        "Resolve the pending approval for the governed side-effect proposal.",
    )
    execution_result, caller_context, executor_result = ops._dispatcher.executor.resolve_approval(
        session,
        approved=True,
        request=executor_request,
    )
    ops._set_execution_state(session, execution_result, caller_context)
    ops._record_result(session, executor_result, next_role=ops._next_role_after_success(session))
    if execution_result.state != GovernedActionState.EXECUTED:
        session.last_verdict = ops._execution_failure_verdict(session, execution_result)
        ops._refresh_session_context(session)
        return {"session": session, "route_hint": "recover", "last_error": None}
    ops._clear_pending_execution(session)
    if session.current_step is not None and session.current_step.kind == TaskStepKind.DYNAMIC:
        ops._refresh_session_context(session)
        return {"session": session, "route_hint": "dynamic_observe", "last_error": None}
    ops._complete_step(session)
    return {"session": session, "route_hint": _active_step_route(session), "last_error": None}


def verify(state: TaskGraphState, ops: TaskGraphOps) -> dict:
    session = state.session
    if session.current_step is None:
        return {"route_hint": "finalize"}
    ops._transition(session, TaskStatus.VERIFYING)
    session.active_verification_spec = session.current_step.verification_spec or session.active_verification_spec
    ops._refresh_memory_runtime_context(
        session,
        role=AgentRole.VERIFIER,
        storage_key=session.current_step.step_id,
    )
    verifier_request = ops._build_request(
        session,
        AgentRole.VERIFIER,
        "Produce an evidence-based verification verdict for the active step.",
    )
    verdict, verifier_result = ops._dispatcher.verifier.verify(session, session.last_observation, verifier_request)
    session.last_verdict = verdict
    next_role = (
        ops._next_role_after_success(session)
        if verdict.status == VerificationStatus.VERIFIED_SUCCESS
        else (AgentRole.RECOVERY if ops._policy.allow_recovery else None)
    )
    ops._record_result(session, verifier_result, next_role=next_role)
    ops._refresh_support_context(session, capability="evaluation")

    if verdict.status == VerificationStatus.VERIFIED_SUCCESS:
        ops._complete_step(session)
        return {"session": session, "route_hint": "writeback_memory", "last_error": None}

    if not ops._policy.allow_recovery:
        ops._transition(session, TaskStatus.FAILED)
        session.completion_verdict = ops._map_completion(verdict.status)
        ops._refresh_session_context(session)
        return {"session": session, "route_hint": "writeback_memory", "last_error": None}

    ops._refresh_session_context(session)
    return {"session": session, "route_hint": "recover", "last_error": None}


def recover(state: TaskGraphState, ops: TaskGraphOps) -> dict:
    session = state.session
    failure_verdict = session.last_verdict
    ops._transition(session, TaskStatus.RECOVERING)
    ops._set_active_model_profile(session, AgentRole.RECOVERY)
    ops._refresh_memory_runtime_context(
        session,
        role=AgentRole.RECOVERY,
        storage_key=session.current_step.step_id if session.current_step is not None else AgentRole.RECOVERY.value,
    )
    recovery_request = ops._build_request(
        session,
        AgentRole.RECOVERY,
        "Handle the failed or blocked path and prepare recovery context.",
    )
    recovery_outcome, recovery_result = ops._dispatcher.recovery.recover(session, failure_verdict, recovery_request)
    session.recovery_outcome = recovery_outcome
    session.recovery_guidance = recovery_outcome.guidance
    session.recovery_execution = recovery_outcome.execution_context
    session.recovery_observation = recovery_outcome.observation
    session.recovery_state = recovery_outcome.summary
    if recovery_outcome.verification_spec is not None:
        session.active_verification_spec = recovery_outcome.verification_spec
    ops._record_result(session, recovery_result, next_role=AgentRole.VERIFIER)
    ops._refresh_session_context(session)
    if recovery_outcome.replan_decision is not None:
        return _route_replan_decision(session, ops, recovery_outcome.replan_decision.decision_type)
    return {"session": session, "route_hint": "verify_recovery", "last_error": None}


def verify_recovery(state: TaskGraphState, ops: TaskGraphOps) -> dict:
    session = state.session
    if session.recovery_outcome is None:
        raise ValueError("TaskGraphRuntime.verify_recovery requires a recovery outcome.")
    ops._transition(session, TaskStatus.VERIFYING)
    recovery_observation = ops._build_recovery_observation(session, session.recovery_outcome)
    if recovery_observation is not None:
        session.last_observation = recovery_observation
    ops._set_active_model_profile(session, AgentRole.VERIFIER)
    verifier_request = ops._build_request(
        session,
        AgentRole.VERIFIER,
        "Produce the final evidence-based verification verdict for the recovery path.",
    )
    verdict, verifier_result = ops._dispatcher.verifier.verify(session, session.last_observation, verifier_request)
    session.last_verdict = verdict
    ops._record_result(session, verifier_result, next_role=None)
    ops._refresh_support_context(session, capability="evaluation")
    if verdict.status == VerificationStatus.VERIFIED_SUCCESS:
        ops._complete_step(session)
    else:
        ops._transition(session, TaskStatus.FAILED)
        session.completion_verdict = ops._map_completion(verdict.status)
    ops._refresh_session_context(session)
    return {"session": session, "route_hint": "writeback_memory", "last_error": None}


def writeback_memory(state: TaskGraphState, ops: TaskGraphOps) -> dict:
    session = state.session
    ops._writeback_memory(session)
    ops._refresh_session_context(session)
    return {"session": session, "route_hint": _active_step_route(session), "last_error": None}


def finalize(state: TaskGraphState, ops: TaskGraphOps) -> dict:
    session = state.session
    if session.current_step is None and session.status not in TERMINAL_STATUSES:
        ops._transition(session, TaskStatus.COMPLETED)
        session.completion_verdict = TaskCompletionVerdict.TASK_COMPLETED
    ops._refresh_session_context(session)
    return {"session": session, "route_hint": "finalize", "last_error": None}


def _active_step_route(session: TaskSession) -> str:
    if session.status in TERMINAL_STATUSES or session.current_step is None:
        return "finalize"
    if session.current_step.kind == TaskStepKind.DYNAMIC:
        return "dynamic_observe"
    if session.current_step.kind == TaskStepKind.RECOVER:
        return "recover"
    raise ValueError(f"Unsupported task step kind: {session.current_step.kind}")


def _dynamic_blocked_verdict(
    session: TaskSession,
    *,
    blocked_reason: str,
    summary: str,
) -> VerificationVerdict:
    target_kind = (
        session.current_step.verification_target_kind
        if session.current_step and session.current_step.verification_target_kind is not None
        else session.target_kind
    )
    target_id = (
        session.current_step.verification_target_id
        if session.current_step and session.current_step.verification_target_id is not None
        else session.target_id
    )
    resolved_target_kind = target_kind or session.target_kind or EntityKind.TASK
    return VerificationVerdict(
        verdict_id=f"task-verdict:{session.session_id}:{blocked_reason}",
        status=VerificationStatus.BLOCKED,
        summary=summary,
        target_kind=resolved_target_kind,
        target_id=target_id or session.session_id,
        unmatched_check_ids=[session.active_verification_spec.success_checks[0].check_id]
        if session.active_verification_spec
        else ["dynamic-step"],
        evidence_refs=[],
        blocked_reason=blocked_reason,
    )


def _route_replan_decision(session: TaskSession, ops: TaskGraphOps, decision_type: ReplanDecisionType) -> dict:
    if decision_type == ReplanDecisionType.RETRY_CURRENT_STEP:
        if session.current_step is not None:
            session.step_policy_iterations[session.current_step.step_id] = 0
        session.last_step_decision = None
        session.recovery_outcome = None
        ops._refresh_session_context(session)
        return {"session": session, "route_hint": _active_step_route(session), "last_error": None}
    if decision_type == ReplanDecisionType.SKIP_CURRENT_STEP:
        session.recovery_outcome = None
        ops._complete_step_without_verification(session)
        ops._refresh_session_context(session)
        return {"session": session, "route_hint": _active_step_route(session), "last_error": None}
    if decision_type == ReplanDecisionType.HANDOFF:
        ops._transition(session, TaskStatus.HANDED_OFF)
        session.completion_verdict = TaskCompletionVerdict.BLOCKED
        ops._refresh_session_context(session)
        return {"session": session, "route_hint": "finalize", "last_error": None}
    ops._transition(session, TaskStatus.FAILED)
    session.completion_verdict = TaskCompletionVerdict.FAILED
    ops._refresh_session_context(session)
    return {"session": session, "route_hint": "writeback_memory", "last_error": None}


__all__ = [
    "TaskGraphOps",
    "activate_step",
    "decide_step",
    "dynamic_execute",
    "dynamic_observe",
    "ensure_plan",
    "finalize",
    "recover",
    "resume_approval",
    "verify",
    "verify_recovery",
    "writeback_memory",
]
