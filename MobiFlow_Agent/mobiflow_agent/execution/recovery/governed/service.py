from __future__ import annotations

from typing import Any
from uuid import uuid4

from mobiflow_agent.execution.recovery.common import resume_pending_execution
from mobiflow_agent.execution.recovery.governed.graph import build_governed_recovery_execution_graph
from mobiflow_agent.execution.recovery.governed.models import (
    GovernedRecoveryApproval,
    GovernedRecoveryExecutionResponse,
)
from mobiflow_agent.platform.adapter import PlatformAdapter
from mobiflow_agent.runtime.checkpointing import (
    RuntimeCheckpointConfig,
    RuntimeCheckpointMode,
    create_checkpointer,
)
from mobiflow_agent.runtime.state import AgentRuntimeState, PendingExecution, RuntimeLifecycle


def build_initial_governed_recovery_state(
    run_target_id: str,
    session_id: str = "mobiflow-agent",
) -> AgentRuntimeState:
    from mobiflow_agent.common.contracts import EntityKind

    return AgentRuntimeState(
        session_id=session_id,
        focus_kind=EntityKind.RUN_TARGET,
        focus_id=run_target_id,
    )


def resume_governed_recovery_execution(
    app: Any,
    config: dict[str, Any],
    persisted_state,
    *,
    approved: bool | None = None,
    expired: bool = False,
):
    return resume_pending_execution(
        app,
        config,
        persisted_state,
        approved=approved,
        expired=expired,
        missing_pending_message="resume_governed_recovery_execution requires a persisted pending execution.",
        missing_decision_message="resume_governed_recovery_execution requires approved=True/False or expired=True.",
    )


class GovernedRecoveryExecutionService:
    def __init__(self, adapter: PlatformAdapter, *, checkpointer: Any | None = None):
        self._adapter = adapter
        self._checkpointer = checkpointer or create_checkpointer(
            RuntimeCheckpointConfig(mode=RuntimeCheckpointMode.MEMORY)
        )
        self._app = build_governed_recovery_execution_graph(adapter, checkpointer=self._checkpointer)

    def start(
        self,
        run_target_id: str,
        *,
        session_id: str = "mobiflow-agent",
        thread_id: str | None = None,
    ) -> GovernedRecoveryExecutionResponse:
        resolved_thread_id = thread_id or self._build_thread_id(run_target_id)
        result = self._app.invoke(
            build_initial_governed_recovery_state(run_target_id, session_id=session_id).model_dump(mode="python"),
            config=self._config(resolved_thread_id),
        )
        state = AgentRuntimeState.model_validate(result)
        return self._build_response(resolved_thread_id, run_target_id, state)

    def resume(
        self,
        thread_id: str,
        *,
        approved: bool | None = None,
        expired: bool = False,
    ) -> GovernedRecoveryExecutionResponse:
        state = self.get_state(thread_id)
        if state.lifecycle != RuntimeLifecycle.AWAITING_APPROVAL:
            raise ValueError(f"governed_recovery thread {thread_id} is not awaiting approval.")
        if state.pending_execution is None:
            raise ValueError(f"governed_recovery thread {thread_id} has no pending execution.")
        if approved is None and not expired:
            raise ValueError("resume() requires approved=True/False or expired=True.")

        result = resume_governed_recovery_execution(
            self._app,
            self._config(thread_id),
            state,
            approved=approved,
            expired=expired,
        )
        next_state = AgentRuntimeState.model_validate(result)
        return self._build_response(thread_id, self._run_target_id(next_state), next_state)

    def get_state(self, thread_id: str) -> AgentRuntimeState:
        snapshot = self._app.get_state(self._config(thread_id))
        if not snapshot.values:
            raise ValueError(f"governed_recovery thread {thread_id} was not found.")
        return AgentRuntimeState.model_validate(snapshot.values)

    @staticmethod
    def _build_thread_id(run_target_id: str) -> str:
        return f"recover-run-target:{run_target_id}:{uuid4().hex}"

    @staticmethod
    def _config(thread_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": thread_id}}

    @staticmethod
    def _run_target_id(state: AgentRuntimeState, pending: PendingExecution | None = None) -> str:
        run_target_id = state.focus_id or (pending.proposal.target_id if pending else None)
        if not run_target_id:
            raise ValueError("governed_recovery response is missing run_target_id.")
        return run_target_id

    @staticmethod
    def _run_id(state: AgentRuntimeState) -> str:
        if state.recovery_execution is not None:
            return state.recovery_execution.source_run_id
        raise ValueError("governed_recovery response is missing run_id.")

    def _build_response(
        self,
        thread_id: str,
        run_target_id: str,
        state: AgentRuntimeState,
    ) -> GovernedRecoveryExecutionResponse:
        pending = state.pending_execution
        run_id = self._run_id(state)
        action_name = self._action_name(state)
        created_run_id = self._created_run_id(state)
        approval_request = None
        if (
            state.lifecycle == RuntimeLifecycle.AWAITING_APPROVAL
            and pending is not None
            and pending.confirmation_id
            and pending.confirmation_summary
        ):
            approval_request = GovernedRecoveryApproval(
                thread_id=thread_id,
                run_target_id=run_target_id,
                run_id=run_id,
                confirmation_id=pending.confirmation_id,
                summary=pending.confirmation_summary,
                expires_at=pending.confirmation_expires_at,
            )

        return GovernedRecoveryExecutionResponse(
            thread_id=thread_id,
            run_target_id=run_target_id,
            run_id=run_id,
            action_name=action_name,
            created_run_id=created_run_id,
            followup_required=self._followup_required(action_name, created_run_id),
            lifecycle=state.lifecycle,
            verdict=state.latest_verdict,
            approval_request=approval_request,
            runtime_state=state,
        )

    @staticmethod
    def _action_name(state: AgentRuntimeState) -> str:
        if state.recovery_execution is not None:
            return state.recovery_execution.action_name
        pending = state.pending_execution
        if pending is not None:
            return pending.proposal.action_tool_name
        raise ValueError("governed_recovery response is missing action_name.")

    @staticmethod
    def _created_run_id(state: AgentRuntimeState) -> str | None:
        if state.recovery_execution is None:
            return None
        return state.recovery_execution.created_run_id

    @staticmethod
    def _followup_required(action_name: str, created_run_id: str | None) -> bool:
        return action_name in {"create_run", "create_single_device_run"} and created_run_id is not None


__all__ = [
    "GovernedRecoveryExecutionService",
    "build_initial_governed_recovery_state",
    "resume_governed_recovery_execution",
]
