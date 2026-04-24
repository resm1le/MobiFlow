from __future__ import annotations


class TaskHarnessError(RuntimeError):
    """Base error for task-first harness failures."""


class TaskHarnessTransitionError(TaskHarnessError):
    """Raised when a harness job is advanced through an invalid state transition."""


class TaskHarnessStoreError(TaskHarnessError):
    """Raised when the harness store cannot persist or load a job."""


class TaskHarnessSerializationError(TaskHarnessStoreError):
    """Raised when a persisted harness job payload cannot be decoded."""


__all__ = [
    "TaskHarnessError",
    "TaskHarnessSerializationError",
    "TaskHarnessStoreError",
    "TaskHarnessTransitionError",
]
