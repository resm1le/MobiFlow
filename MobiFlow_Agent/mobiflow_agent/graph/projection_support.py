from __future__ import annotations

from mobiflow_agent.runtime.state import AgentRuntimeState, RuntimeLifecycle
from mobiflow_agent.task.plan import TaskStatus
from mobiflow_agent.task.session import TaskSession


class TaskGraphRuntimeProjectionMixin:
    def export_runtime_state(self, session: TaskSession) -> AgentRuntimeState:
        focus_kind, focus_id = self._focus(session)
        audit_refs = []
        if session.pending_execution and session.pending_execution.audit is not None:
            audit_refs.append(session.pending_execution.audit)
        if session.last_execution_result and session.last_execution_result.audit is not None:
            audit_refs.append(session.last_execution_result.audit)
        known_resource_handles = list(session.last_observation.resource_handles) if session.last_observation is not None else []
        return AgentRuntimeState(
            session_id=session.session_id,
            lifecycle=self._to_runtime_lifecycle(session.status),
            turn_index=max(len(session.status_history) - 1, 0),
            step_index=session.current_step_index,
            active_contract=session.contract,
            focus_kind=focus_kind,
            focus_id=focus_id,
            latest_observation=session.last_observation,
            pending_execution=session.pending_execution,
            recovery_execution=session.recovery_execution,
            recovery_observation=session.recovery_observation,
            recovery_summary=session.recovery_outcome.summary if session.recovery_outcome is not None else session.recovery_state,
            active_verification=session.active_verification_spec,
            latest_verdict=session.last_verdict,
            known_resource_handles=known_resource_handles,
            audit_refs=audit_refs,
        )

    def apply_runtime_state(self, session: TaskSession, runtime_state: AgentRuntimeState) -> TaskSession:
        session.status = self._from_runtime_lifecycle(runtime_state.lifecycle)
        if not session.status_history or session.status_history[-1] != session.status:
            session.status_history.append(session.status)
        session.current_step_index = runtime_state.step_index
        if session.plan is not None:
            if runtime_state.step_index >= len(session.plan.steps):
                raise ValueError("Runtime state step_index is outside the active TaskPlan.")
            session.current_step = session.plan.steps[runtime_state.step_index]
        session.target_kind = session.target_kind or runtime_state.focus_kind
        session.target_id = session.target_id or runtime_state.focus_id
        session.last_observation = runtime_state.latest_observation
        session.pending_execution = runtime_state.pending_execution
        session.recovery_execution = runtime_state.recovery_execution
        session.recovery_observation = runtime_state.recovery_observation
        session.recovery_state = runtime_state.recovery_summary
        session.active_verification_spec = runtime_state.active_verification
        session.last_verdict = runtime_state.latest_verdict
        return session

    @staticmethod
    def _to_runtime_lifecycle(status: TaskStatus) -> RuntimeLifecycle:
        mapping = {
            TaskStatus.CREATED: RuntimeLifecycle.DRAFTING,
            TaskStatus.PLANNING: RuntimeLifecycle.DRAFTING,
            TaskStatus.OBSERVING: RuntimeLifecycle.OBSERVING,
            TaskStatus.AWAITING_APPROVAL: RuntimeLifecycle.AWAITING_APPROVAL,
            TaskStatus.EXECUTING: RuntimeLifecycle.EXECUTING,
            TaskStatus.VERIFYING: RuntimeLifecycle.VERIFYING,
            TaskStatus.RECOVERING: RuntimeLifecycle.OBSERVING,
            TaskStatus.COMPLETED: RuntimeLifecycle.COMPLETED,
            TaskStatus.FAILED: RuntimeLifecycle.BLOCKED,
            TaskStatus.HANDED_OFF: RuntimeLifecycle.BLOCKED,
        }
        return mapping[status]

    @staticmethod
    def _from_runtime_lifecycle(lifecycle: RuntimeLifecycle) -> TaskStatus:
        mapping = {
            RuntimeLifecycle.DRAFTING: TaskStatus.PLANNING,
            RuntimeLifecycle.OBSERVING: TaskStatus.OBSERVING,
            RuntimeLifecycle.AWAITING_APPROVAL: TaskStatus.AWAITING_APPROVAL,
            RuntimeLifecycle.EXECUTING: TaskStatus.EXECUTING,
            RuntimeLifecycle.VERIFYING: TaskStatus.VERIFYING,
            RuntimeLifecycle.COMPLETED: TaskStatus.COMPLETED,
            RuntimeLifecycle.BLOCKED: TaskStatus.FAILED,
        }
        return mapping[lifecycle]


__all__ = ["TaskGraphRuntimeProjectionMixin"]
