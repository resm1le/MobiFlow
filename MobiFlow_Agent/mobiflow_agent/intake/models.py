from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import Field

from mobiflow_agent.common.contracts import ApprovalMode, EntityKind, StrictModel
from mobiflow_agent.task.session import TaskSession


class TaskIntakeStatus(str, Enum):
    READY = "ready"
    NEEDS_CLARIFICATION = "needs_clarification"
    REJECTED = "rejected"


class TaskIntakeSpec(StrictModel):
    raw_goal: str = Field(min_length=1)
    normalized_goal: str = Field(min_length=1)
    intent: str | None = None
    scenario_id: str | None = None
    target_kind: EntityKind | None = None
    target_id: str | None = None
    device_id: str | None = None
    app_package: str | None = None
    verification_template: str | None = None
    verification_params: dict[str, Any] = Field(default_factory=dict)
    allowed_actions: list[str] = Field(default_factory=list)
    approval_mode: ApprovalMode = ApprovalMode.ON_RISK
    missing_fields: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    needs_confirmation: bool = True
    risk_flags: list[str] = Field(default_factory=list)


class TaskIntakeResult(StrictModel):
    status: TaskIntakeStatus
    spec: TaskIntakeSpec | None = None
    session: TaskSession | None = None
    clarification_questions: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    trace_refs: list[str] = Field(default_factory=list)


class TaskIntakeValidationResult(StrictModel):
    accepted: bool
    issues: list[str] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)


__all__ = [
    "TaskIntakeResult",
    "TaskIntakeSpec",
    "TaskIntakeStatus",
    "TaskIntakeValidationResult",
]
