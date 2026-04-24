from __future__ import annotations

from enum import Enum

from pydantic import Field, model_validator

from mobiflow_agent.common.contracts import EntityKind, ExecutionProposal, StrictModel, VerificationSpec, VerificationVerdict
from mobiflow_agent.execution.followup.driver import RecoveryFollowupDriverDecision
from mobiflow_agent.runtime.context import ContextHandoff
from mobiflow_agent.runtime.state import AgentRuntimeState
from mobiflow_agent.task.completion import TaskCompletionVerdict
from mobiflow_agent.task.session import TaskSession

TASK_HARNESS_SCHEMA_VERSION = 1


class TaskHarnessStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    FAILED = "failed"
    HANDED_OFF = "handed_off"


class TaskHarnessJobPolicy(StrictModel):
    wake_interval_seconds: int = Field(default=30, ge=1)
    max_heartbeat_ticks: int = Field(default=3, ge=1)
    continue_on_handoff: bool = False


class TaskHarnessRequest(StrictModel):
    goal: str = Field(min_length=1)
    target_kind: EntityKind | None = None
    target_id: str | None = None
    proposal: ExecutionProposal | None = None
    verification_spec: VerificationSpec | None = None
    handoff: ContextHandoff | None = None
    policy: TaskHarnessJobPolicy = Field(default_factory=TaskHarnessJobPolicy)


class TaskHarnessApprovalRequest(StrictModel):
    confirmation_id: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    expires_at: int | None = Field(default=None, ge=0)


class TaskHarnessResponse(StrictModel):
    job_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    status: TaskHarnessStatus
    completion_verdict: TaskCompletionVerdict | None = None
    runtime_state: AgentRuntimeState | None = None
    context_handoff: ContextHandoff | None = None
    approval_request: TaskHarnessApprovalRequest | None = None
    latest_verdict: VerificationVerdict | None = None
    decision: RecoveryFollowupDriverDecision | None = None
    summary: str = Field(min_length=1)
    next_wakeup_at: int | None = Field(default=None, ge=0)
    error: str | None = None
    is_terminal: bool = False
    heartbeat_attempts: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def normalize_terminal_flag(self) -> "TaskHarnessResponse":
        self.is_terminal = self.status in {
            TaskHarnessStatus.COMPLETED,
            TaskHarnessStatus.FAILED,
            TaskHarnessStatus.HANDED_OFF,
        }
        return self


class TaskHarnessJob(StrictModel):
    job_id: str = Field(min_length=1)
    schema_version: int = Field(default=TASK_HARNESS_SCHEMA_VERSION, ge=1)
    request: TaskHarnessRequest | None = None
    session: TaskSession | None = None
    runtime_state: AgentRuntimeState | None = None
    imported_handoff: ContextHandoff | None = None
    status: TaskHarnessStatus = TaskHarnessStatus.PENDING
    next_wakeup_at: int | None = Field(default=None, ge=0)
    policy: TaskHarnessJobPolicy = Field(default_factory=TaskHarnessJobPolicy)
    last_response: TaskHarnessResponse | None = None
    heartbeat_attempts: int = Field(default=0, ge=0)
    created_at_ms: int = Field(default=0, ge=0)
    updated_at_ms: int = Field(default=0, ge=0)
    last_error: str | None = None
    failure_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_job(self) -> "TaskHarnessJob":
        if self.schema_version != TASK_HARNESS_SCHEMA_VERSION:
            raise ValueError(f"Unsupported TaskHarnessJob schema_version: {self.schema_version}.")
        if self.status == TaskHarnessStatus.RUNNING and self.session is None:
            raise ValueError("TaskHarnessJob running status requires a persisted session.")
        if self.status == TaskHarnessStatus.AWAITING_APPROVAL and self.session is None:
            raise ValueError("TaskHarnessJob awaiting approval requires a persisted session.")
        if self.status == TaskHarnessStatus.SCHEDULED:
            if self.next_wakeup_at is None:
                raise ValueError("TaskHarnessJob scheduled status requires next_wakeup_at.")
            if self.imported_handoff is None and self.session is None:
                raise ValueError("TaskHarnessJob scheduled status requires session or imported_handoff.")
        if self.status in {TaskHarnessStatus.COMPLETED, TaskHarnessStatus.FAILED, TaskHarnessStatus.HANDED_OFF}:
            if self.next_wakeup_at is not None:
                raise ValueError("Terminal TaskHarnessJob status must not keep next_wakeup_at.")
        return self


__all__ = [
    "TASK_HARNESS_SCHEMA_VERSION",
    "TaskHarnessApprovalRequest",
    "TaskHarnessJob",
    "TaskHarnessJobPolicy",
    "TaskHarnessRequest",
    "TaskHarnessResponse",
    "TaskHarnessStatus",
]
