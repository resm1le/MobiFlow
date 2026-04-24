from __future__ import annotations

from typing import Any

from mobiflow_agent.agents.executor import ExecutorAgent
from mobiflow_agent.agents.observer import ObserverAgent
from mobiflow_agent.agents.planner import PlannerAgent
from mobiflow_agent.agents.recovery import RecoveryAgent
from mobiflow_agent.agents.step_policy import StepPolicyAgent
from mobiflow_agent.agents.verifier import VerifierAgent
from mobiflow_agent.common.contracts import EntityKind, ExecutionProposal, VerificationSpec
from mobiflow_agent.control.policy import TaskControlPolicy
from mobiflow_agent.memory.runtime import TaskMemoryRuntime
from mobiflow_agent.model.config import RoleModelPolicy
from mobiflow_agent.model.runtime import ModelRegistry
from mobiflow_agent.runtime.context import ContextCompressionService, ContextHandoff
from mobiflow_agent.task.plan import TaskStatus
from mobiflow_agent.task.session import TaskSession

from .builder import build_task_orchestration_graph
from .state import TaskGraphState
from .support import SupportHook, TaskGraphSupport


class TaskGraphRuntime(TaskGraphSupport):
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
        checkpointer: Any | None = None,
    ) -> None:
        super().__init__(
            planner_agent=planner_agent,
            observer_agent=observer_agent,
            step_policy_agent=step_policy_agent,
            executor_agent=executor_agent,
            verifier_agent=verifier_agent,
            recovery_agent=recovery_agent,
            policy=policy,
            memory_support=memory_support,
            memory_runtime=memory_runtime,
            evaluation_support=evaluation_support,
            role_model_policy=role_model_policy,
            model_registry=model_registry,
            context_compressor=context_compressor,
        )
        self._graph_app = build_task_orchestration_graph(self, checkpointer=checkpointer)

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
        return super().create_session(
            goal,
            target_kind=target_kind,
            target_id=target_id,
            proposal=proposal,
            verification_spec=verification_spec,
            session_id=session_id,
            handoff=handoff,
        )

    def run(self, session: TaskSession, *, config: dict[str, Any] | None = None) -> TaskSession:
        if session.status in {
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.AWAITING_APPROVAL,
            TaskStatus.HANDED_OFF,
        }:
            return session
        return self._invoke_graph(TaskGraphState(session=session), config=config)

    def resume(
        self,
        session: TaskSession,
        *,
        approved: bool | None = None,
        expired: bool = False,
        config: dict[str, Any] | None = None,
    ) -> TaskSession:
        if session.status != TaskStatus.AWAITING_APPROVAL:
            raise ValueError("TaskGraphRuntime.resume requires a session awaiting approval.")
        if session.pending_execution is None:
            raise ValueError("TaskGraphRuntime.resume requires pending execution on the session.")
        if approved is None and not expired:
            raise ValueError("resume() requires approved=True/False or expired=True.")
        return self._invoke_graph(
            TaskGraphState(
                session=session,
                resume_decision=approved,
                resume_expired=expired,
            ),
            config=config,
        )

    def _invoke_graph(
        self,
        state: TaskGraphState,
        *,
        config: dict[str, Any] | None = None,
    ) -> TaskSession:
        resolved_config = config or {"configurable": {"thread_id": state.session.session_id}}
        result = self._graph_app.invoke(state, config=resolved_config)
        if isinstance(result, TaskGraphState):
            return result.session
        return TaskGraphState.model_validate(result).session


__all__ = ["TaskGraphRuntime"]
