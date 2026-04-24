from __future__ import annotations

from typing import Any, Callable

from mobiflow_agent.task.session import TaskSession

SupportHook = Callable[[TaskSession], dict[str, Any] | None]

__all__ = ["SupportHook"]
