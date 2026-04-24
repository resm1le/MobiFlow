from enum import Enum


class TaskCompletionVerdict(str, Enum):
    STEP_COMPLETED = "step_completed"
    TASK_COMPLETED = "task_completed"
    UNKNOWN = "unknown"
    BLOCKED = "blocked"
    FAILED = "failed"
