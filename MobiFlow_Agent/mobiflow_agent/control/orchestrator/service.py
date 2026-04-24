from __future__ import annotations

from mobiflow_agent.graph.runtime import TaskGraphRuntime
from mobiflow_agent.graph.support import SupportHook


class TaskOrchestratorService(TaskGraphRuntime):
    """Compatibility name for the graph-backed task runtime."""


__all__ = ["SupportHook", "TaskOrchestratorService"]
