from __future__ import annotations

from mobiflow_agent.agents.contracts import AgentRole
from mobiflow_agent.task.session import TaskSession


class TaskGraphMemorySupportMixin:
    def _refresh_support_context(self, session: TaskSession, *, capability: str) -> None:
        if session.current_step is None:
            return
        if capability == "memory":
            if self._memory_support is None:
                return
            payload = self._memory_support(session)
            if payload is not None:
                session.memory_context[session.current_step.step_id] = payload
                self._refresh_session_context(session)
            return
        if capability == "evaluation":
            if self._evaluation_support is None:
                return
            payload = self._evaluation_support(session)
            if payload is not None:
                session.evaluation_context[session.current_step.step_id] = payload
                self._refresh_session_context(session)
            return
        raise ValueError(f"Unknown support capability: {capability}")

    def _refresh_memory_runtime_context(
        self,
        session: TaskSession,
        *,
        role: AgentRole,
        storage_key: str,
    ) -> None:
        if getattr(self, "_memory_runtime", None) is None:
            return
        context = self._memory_runtime.prepare_context(session, role=role)
        session.memory_context[storage_key] = context.model_dump(mode="python")
        self._refresh_session_context(session)

    def _writeback_memory(self, session: TaskSession) -> None:
        if getattr(self, "_memory_runtime", None) is None:
            return
        result = self._memory_runtime.writeback_session(session)
        session.memory_context["memory_writeback:last"] = result.model_dump(mode="python")


__all__ = ["TaskGraphMemorySupportMixin"]
