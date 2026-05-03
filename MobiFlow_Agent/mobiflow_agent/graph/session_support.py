from __future__ import annotations

from mobiflow_agent.agents.contracts import AgentRole
from mobiflow_agent.agents.executor import ExecutorAgent
from mobiflow_agent.agents.observer import ObserverAgent
from mobiflow_agent.agents.planner import PlannerAgent
from mobiflow_agent.agents.recovery import RecoveryAgent
from mobiflow_agent.agents.step_policy import StepPolicyAgent
from mobiflow_agent.agents.verifier import VerifierAgent
from mobiflow_agent.common.contracts import EntityKind, ExecutionProposal, VerificationSpec
from mobiflow_agent.common.ids import build_task_session_id
from mobiflow_agent.control.dispatcher import TaskAgentDispatcher
from mobiflow_agent.control.policy import TaskControlPolicy
from mobiflow_agent.memory.runtime import TaskMemoryRuntime
from mobiflow_agent.model.config import RoleModelPolicy
from mobiflow_agent.model.runtime import ModelRegistry, ModelRuntime
from mobiflow_agent.runtime.context import ContextCompressionService, ContextHandoff
from mobiflow_agent.task.completion import TaskCompletionVerdict
from mobiflow_agent.task.plan import TaskStatus, TaskStep, TaskStepKind
from mobiflow_agent.task.session import TaskSession

from .support_types import SupportHook


class TaskGraphSessionSupportMixin:
    def __init__(
        self,
        *,
        planner_agent: PlannerAgent | None = None,
        observer_agent: ObserverAgent | None = None,
        step_policy_agent: StepPolicyAgent | None = None,
        executor_agent: ExecutorAgent | None = None,
        verifier_agent: VerifierAgent | None = None,
        recovery_agent: RecoveryAgent | None = None,
        policy: TaskControlPolicy | None = None,
        memory_support: SupportHook | None = None,
        memory_runtime: TaskMemoryRuntime | None = None,
        evaluation_support: SupportHook | None = None,
        role_model_policy: RoleModelPolicy | None = None,
        model_registry: ModelRegistry | None = None,
        context_compressor: ContextCompressionService | None = None,
    ):
        self._role_model_policy = role_model_policy or RoleModelPolicy()
        self._context_compressor = context_compressor or ContextCompressionService()
        self._model_runtime = (
            ModelRuntime(
                model_registry,
                role_policy=self._role_model_policy,
                context_compressor=self._context_compressor,
            )
            if model_registry is not None
            else None
        )
        self._dispatcher = TaskAgentDispatcher(
            planner=planner_agent or PlannerAgent(model_client=self._model_runtime),
            observer=observer_agent or ObserverAgent(),
            step_policy=step_policy_agent or StepPolicyAgent(),
            executor=executor_agent,
            verifier=verifier_agent or VerifierAgent(model_client=self._model_runtime),
            recovery=recovery_agent or RecoveryAgent(model_client=self._model_runtime),
        )
        self._dispatcher.planner.bind_model_runtime(self._model_runtime)
        self._dispatcher.step_policy.bind_model_runtime(self._model_runtime)
        self._dispatcher.verifier.bind_model_runtime(self._model_runtime)
        self._dispatcher.recovery.bind_model_runtime(self._model_runtime)
        self._policy = policy or TaskControlPolicy()
        self._memory_runtime = memory_runtime
        if self._memory_runtime is not None:
            self._memory_runtime.bind_model_runtime(self._model_runtime)
        self._memory_support = memory_support
        self._evaluation_support = evaluation_support

    def create_session(
        self,
        goal: str,
        *,
        target_kind: EntityKind | None = None,
        target_id: str | None = None,
        proposal: ExecutionProposal | None = None,
        verification_spec: VerificationSpec | None = None,
        session_id: str | None = None,
        handoff: ContextHandoff | None = None,
    ) -> TaskSession:
        session = TaskSession(
            session_id=session_id or build_task_session_id(),
            goal=goal,
            target_kind=target_kind,
            target_id=target_id,
            initial_proposal=proposal,
            initial_verification_spec=verification_spec,
        )
        if handoff is not None:
            self.apply_context_handoff(session, handoff)
        return session

    def export_context_handoff(self, session: TaskSession) -> ContextHandoff:
        if session.session_digest is None:
            self._refresh_session_context(session)
        return self._context_compressor.export_context_handoff(session)

    def apply_context_handoff(self, session: TaskSession, handoff: ContextHandoff) -> TaskSession:
        return self._context_compressor.apply_context_handoff(session, handoff)

    def _initialize_plan(self, session: TaskSession) -> None:
        self._refresh_memory_runtime_context(session, role=AgentRole.PLANNER, storage_key=AgentRole.PLANNER.value)
        self._set_active_model_profile(session, AgentRole.PLANNER)
        planner_request = self._build_request(session, AgentRole.PLANNER, "Create the active task contract and plan.")
        contract, plan, planner_result = self._dispatcher.planner.plan(
            session_id=session.session_id,
            goal=session.goal,
            target_kind=session.target_kind,
            target_id=session.target_id,
            proposal=session.initial_proposal,
            verification_spec=session.initial_verification_spec,
            request=planner_request,
            session=session,
        )
        session.contract = contract
        session.plan = plan
        self._transition(session, TaskStatus.PLANNING)
        self._refresh_session_context(session)
        self._activate_step(session, 0)
        self._record_result(session, planner_result, next_role=self._role_for_step(session.current_step))

    def _activate_step(self, session: TaskSession, step_index: int) -> None:
        if session.plan is None:
            raise ValueError("TaskGraphRuntime requires a plan before activating a step.")
        session.current_step_index = step_index
        session.current_step = session.plan.steps[step_index]
        session.active_verification_spec = session.current_step.verification_spec or session.initial_verification_spec
        self._refresh_support_context(session, capability="memory")
        self._set_active_model_profile(session, self._role_for_step(session.current_step))
        self._refresh_session_context(session)

    def _complete_step(self, session: TaskSession) -> None:
        if session.plan is None or session.current_step is None:
            raise ValueError("TaskGraphRuntime cannot complete a step without an active plan and step.")
        self._refresh_session_context(session)
        if self._has_next_step(session):
            session.completion_verdict = TaskCompletionVerdict.STEP_COMPLETED
            self._activate_step(session, session.current_step_index + 1)
            return
        self._transition(session, TaskStatus.COMPLETED)
        session.completion_verdict = TaskCompletionVerdict.TASK_COMPLETED
        self._refresh_session_context(session)

    def _complete_step_without_verification(self, session: TaskSession) -> None:
        if session.plan is None or session.current_step is None:
            raise ValueError("TaskGraphRuntime cannot skip a step without an active plan and step.")
        if self._has_next_step(session):
            session.completion_verdict = TaskCompletionVerdict.STEP_COMPLETED
            self._activate_step(session, session.current_step_index + 1)
            return
        self._transition(session, TaskStatus.FAILED)
        session.completion_verdict = TaskCompletionVerdict.UNKNOWN
        self._refresh_session_context(session)

    @staticmethod
    def _has_next_step(session: TaskSession) -> bool:
        return session.plan is not None and session.current_step_index + 1 < len(session.plan.steps)

    @staticmethod
    def _role_for_step(step: TaskStep | None) -> AgentRole | None:
        if step is None:
            return None
        if step.kind == TaskStepKind.DYNAMIC:
            return AgentRole.OBSERVER
        if step.kind == TaskStepKind.RECOVER:
            return AgentRole.RECOVERY
        return None

    def _next_role_after_success(self, session: TaskSession) -> AgentRole | None:
        if not self._has_next_step(session) or session.plan is None:
            return None
        return self._role_for_step(session.plan.steps[session.current_step_index + 1])

    @staticmethod
    def _transition(session: TaskSession, status: TaskStatus) -> None:
        session.status = status
        if not session.status_history or session.status_history[-1] != status:
            session.status_history.append(status)

    def _set_active_model_profile(self, session: TaskSession, role: AgentRole | None) -> None:
        if role is None:
            session.active_model_profile = None
            return
        session.active_model_profile = self._role_model_policy.resolve(role)

    def _refresh_session_context(self, session: TaskSession) -> None:
        history_summarizer = None
        if self._model_runtime is not None and session.active_model_profile is not None:
            profile = self._model_runtime.get_profile(session.active_model_profile)
            if profile.settings.summary_profile is not None:
                history_summarizer = (
                    lambda steps: self._model_runtime.summarize_history(
                        steps,
                        profile_name=profile.settings.summary_profile,
                    )
                )
        self._context_compressor.refresh_session_context(
            session,
            history_summarizer=history_summarizer,
        )


__all__ = ["TaskGraphSessionSupportMixin"]
