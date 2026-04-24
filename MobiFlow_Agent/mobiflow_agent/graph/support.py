from __future__ import annotations

from .execution_support import TaskGraphExecutionSupportMixin
from .memory_support import TaskGraphMemorySupportMixin
from .projection_support import TaskGraphRuntimeProjectionMixin
from .recovery_support import TaskGraphRecoverySupportMixin
from .request_support import TaskGraphRequestSupportMixin
from .session_support import TaskGraphSessionSupportMixin
from .support_types import SupportHook


class TaskGraphSupport(
    TaskGraphRuntimeProjectionMixin,
    TaskGraphExecutionSupportMixin,
    TaskGraphMemorySupportMixin,
    TaskGraphRecoverySupportMixin,
    TaskGraphRequestSupportMixin,
    TaskGraphSessionSupportMixin,
):
    """Composed support operations used by LangGraph task nodes."""


__all__ = ["SupportHook", "TaskGraphSupport"]
