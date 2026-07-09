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


__all__ = ["TaskGraphRuntimeProjectionMixin"]
