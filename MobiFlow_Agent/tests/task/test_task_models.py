from mobiflow_agent.common.contracts import EntityKind, ExecutionProposal, VerificationCheck, VerificationSpec
from mobiflow_agent.model.telemetry import ModelInvocationTrace
from mobiflow_agent.platform.types import GovernedActionResult, GovernedActionState
from mobiflow_agent.runtime.state import CallerContext, ConfirmationState, PendingExecution
from mobiflow_agent.task.completion import TaskCompletionVerdict
from mobiflow_agent.task.plan import TaskPlan, TaskStatus, TaskStep, TaskStepKind
from mobiflow_agent.task.session import TaskSession


def test_task_plan_and_session_roundtrip() -> None:
    proposal = ExecutionProposal(
        proposal_id="proposal-1",
        action_tool_name="cancel_run",
        arguments={"runId": "run-123"},
        target_kind=EntityKind.RUN,
        target_id="run-123",
        rationale="Cancel the blocked run.",
    )
    verification_spec = VerificationSpec(
        verification_id="verification:run:run-123",
        target_kind=EntityKind.RUN,
        target_id="run-123",
        success_checks=[
            VerificationCheck(
                check_id="has-evidence",
                description="The task concludes with evidence-backed verification.",
                evidence_hint="observation evidence",
            )
        ],
    )
    steps = [
        TaskStep(
            step_id="step-1",
            kind=TaskStepKind.OBSERVE,
            goal="Observe the blocked run",
            verification_target_kind=EntityKind.RUN,
            verification_target_id="run-123",
        ),
        TaskStep(
            step_id="step-2",
            kind=TaskStepKind.EXECUTE,
            goal="Cancel the blocked run",
            verification_target_kind=EntityKind.RUN,
            verification_target_id="run-123",
            allowed_side_effects=["cancel_run"],
            proposal=proposal,
        ),
        TaskStep(
            step_id="step-3",
            kind=TaskStepKind.VERIFY,
            goal="Verify the run outcome",
            verification_target_kind=EntityKind.RUN,
            verification_target_id="run-123",
            verification_spec=verification_spec,
        ),
    ]
    plan = TaskPlan(
        plan_id="plan-1",
        summary="Multi-step plan",
        steps=steps,
    )
    pending_execution = PendingExecution(
        proposal=proposal,
        caller_context=CallerContext(
            session_id="session-1",
            agent_task_id="session-1",
            turn_id="3",
            step_id="step-2",
        ),
        confirmation_state=ConfirmationState.REQUIRED,
        confirmation_id="confirm-1",
        confirmation_summary="Approve the cancel action.",
    )
    session = TaskSession(
        session_id="session-1",
        goal="Recover the blocked run",
        status=TaskStatus.AWAITING_APPROVAL,
        status_history=[
            TaskStatus.CREATED,
            TaskStatus.PLANNING,
            TaskStatus.OBSERVING,
            TaskStatus.EXECUTING,
            TaskStatus.AWAITING_APPROVAL,
        ],
        target_kind=EntityKind.RUN,
        target_id="run-123",
        initial_proposal=proposal,
        initial_verification_spec=verification_spec,
        plan=plan,
        current_step_index=1,
        current_step=steps[1],
        active_verification_spec=verification_spec,
        last_execution_result=GovernedActionResult(
            state=GovernedActionState.APPROVAL_REQUIRED,
            proposal_id="proposal-1",
            action_tool_name="cancel_run",
            confirmation_id="confirm-1",
            confirmation_summary="Approve the cancel action.",
        ),
        pending_execution=pending_execution,
        memory_context={"step-1": {"source": "memory"}},
        evaluation_context={"step-3": {"source": "evaluation"}},
        model_trace=[
            ModelInvocationTrace(
                invocation_id="model-invocation-1",
                profile_name="planner-profile",
                provider="noop",
                model="noop-model",
                role="planner",
                latency_ms=1,
            )
        ],
        active_model_profile="executor-profile",
        completion_verdict=TaskCompletionVerdict.STEP_COMPLETED,
    )

    restored = TaskSession.model_validate(session.model_dump(mode="python"))

    assert restored.session_id == "session-1"
    assert restored.plan is not None
    assert restored.plan.steps[1].proposal is not None
    assert restored.plan.steps[1].proposal.action_tool_name == "cancel_run"
    assert restored.pending_execution is not None
    assert restored.pending_execution.confirmation_id == "confirm-1"
    assert restored.active_verification_spec is not None
    assert restored.active_verification_spec.verification_id == "verification:run:run-123"
    assert restored.model_trace[0].profile_name == "planner-profile"
    assert restored.active_model_profile == "executor-profile"
    assert restored.completion_verdict == TaskCompletionVerdict.STEP_COMPLETED
