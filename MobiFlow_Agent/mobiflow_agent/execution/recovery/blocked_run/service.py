from __future__ import annotations

from typing import Any
from uuid import uuid4

from mobiflow_agent.common.contracts import EntityKind
from mobiflow_agent.execution.recovery.blocked_run.graph import build_cancel_blocked_run_graph
from mobiflow_agent.execution.recovery.blocked_run.models import (
    CancelBlockedRunApproval,
    CancelBlockedRunResponse,
)
from mobiflow_agent.execution.recovery.common import resume_pending_execution
from mobiflow_agent.platform.adapter import PlatformAdapter
from mobiflow_agent.runtime.checkpointing import (
    RuntimeCheckpointConfig,
    RuntimeCheckpointMode,
    create_checkpointer,
)
from mobiflow_agent.runtime.state import AgentRuntimeState, PendingExecution, RuntimeLifecycle


def build_initial_cancel_run_state(run_id: str, session_id: str = "mobiflow-agent") -> AgentRuntimeState:
    return AgentRuntimeState(
        session_id=session_id,
        focus_kind=EntityKind.RUN,
        focus_id=run_id,
    )


def resume_cancel_blocked_run(
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
        missing_pending_message="resume_cancel_blocked_run requires a persisted pending execution.",
        missing_decision_message="resume_cancel_blocked_run requires approved=True/False or expired=True.",
    )


class CancelBlockedRunService:
    def __init__(self, adapter: PlatformAdapter, *, checkpointer: Any | None = None):
        self._adapter = adapter
        self._checkpointer = checkpointer or create_checkpointer(
            RuntimeCheckpointConfig(mode=RuntimeCheckpointMode.MEMORY)
        )
        self._app = build_cancel_blocked_run_graph(adapter, checkpointer=self._checkpointer)

    def start(
        self,
        run_id: str,
        *,
        session_id: str = "mobiflow-agent",
        thread_id: str | None = None,
    ) -> CancelBlockedRunResponse:
        resolved_thread_id = thread_id or self._build_thread_id(run_id)
        result = self._app.invoke(
            build_initial_cancel_run_state(run_id, session_id=session_id).model_dump(mode="python"),
            config=self._config(resolved_thread_id),
        )
        state = AgentRuntimeState.model_validate(result)
        return self._build_response(resolved_thread_id, run_id, state)

    def resume(
        self,
        thread_id: str,
        *,
        approved: bool | None = None,
        expired: bool = False,
    ) -> CancelBlockedRunResponse:
        state = self.get_state(thread_id)
        if state.lifecycle != RuntimeLifecycle.AWAITING_APPROVAL:
            raise ValueError(f"cancel_blocked_run thread {thread_id} is not awaiting approval.")
        if state.pending_execution is None:
            raise ValueError(f"cancel_blocked_run thread {thread_id} has no pending execution.")
        if approved is None and not expired:
            raise ValueError("resume() requires approved=True/False or expired=True.")

        result = resume_cancel_blocked_run(
            self._app,
            self._config(thread_id),
            state,
            approved=approved,
            expired=expired,
        )
        next_state = AgentRuntimeState.model_validate(result)
        return self._build_response(thread_id, self._run_id(next_state, state.pending_execution), next_state)

    def get_state(self, thread_id: str) -> AgentRuntimeState:
        snapshot = self._app.get_state(self._config(thread_id))
        if not snapshot.values:
            raise ValueError(f"cancel_blocked_run thread {thread_id} was not found.")
        return AgentRuntimeState.model_validate(snapshot.values)

    @staticmethod
    def _build_thread_id(run_id: str) -> str:
        return f"cancel-run:{run_id}:{uuid4().hex}"

    @staticmethod
    def _config(thread_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": thread_id}}

    @staticmethod
    def _run_id(state: AgentRuntimeState, pending: PendingExecution | None = None) -> str:
        run_id = state.focus_id or (pending.proposal.target_id if pending else None)
        if not run_id:
            raise ValueError("cancel_blocked_run response is missing run_id.")
        return run_id

    def _build_response(
        self,
        thread_id: str,
        run_id: str,
        state: AgentRuntimeState,
    ) -> CancelBlockedRunResponse:
        pending = state.pending_execution
        approval_request = None
        if (
            state.lifecycle == RuntimeLifecycle.AWAITING_APPROVAL
            and pending is not None
            and pending.confirmation_id
            and pending.confirmation_summary
        ):
            approval_request = CancelBlockedRunApproval(
                thread_id=thread_id,
                run_id=run_id,
                confirmation_id=pending.confirmation_id,
                summary=pending.confirmation_summary,
                expires_at=pending.confirmation_expires_at,
            )

        return CancelBlockedRunResponse(
            thread_id=thread_id,
            run_id=run_id,
            lifecycle=state.lifecycle,
            verdict=state.latest_verdict,
            approval_request=approval_request,
            runtime_state=state,
        )


__all__ = [
    "CancelBlockedRunService",
    "build_initial_cancel_run_state",
    "resume_cancel_blocked_run",
]
