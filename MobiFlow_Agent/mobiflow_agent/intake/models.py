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
    test_case: "TestCase | None" = None
    session: TaskSession | None = None
    clarification_questions: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    trace_refs: list[str] = Field(default_factory=list)


class TaskIntakeValidationResult(StrictModel):
    accepted: bool
    issues: list[str] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)


class AssertionPredicate(str, Enum):
    EXISTS = "exists"
    NOT_EXISTS = "not_exists"
    EQUALS = "equals"
    CONTAINS = "contains"
    ANY_EQUALS = "any_equals"
    ANY_CONTAINS = "any_contains"


class OutcomeOrigin(str, Enum):
    MODEL_SYNTHESIZED = "model_synthesized"
    USER_AUTHORED = "user_authored"
    TEMPLATE = "template"


class ExpectedOutcome(StrictModel):
    raw_text: str = Field(min_length=1)
    predicate: AssertionPredicate
    observation_fact_id: str | None = None
    field_path: str = Field(min_length=1)
    expected_value: Any | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    origin: OutcomeOrigin = OutcomeOrigin.MODEL_SYNTHESIZED


class TestStep(StrictModel):
    raw_text: str = Field(min_length=1)
    hint_action: str | None = None


class TestCase(StrictModel):
    case_id: str = Field(min_length=1)
    raw_goal: str = Field(min_length=1)
    normalized_goal: str = Field(min_length=1)
    steps: list[TestStep] = Field(default_factory=list)
    expected_outcomes: list[ExpectedOutcome] = Field(default_factory=list)
    target_app: str | None = None
    approval_mode: ApprovalMode = ApprovalMode.ON_RISK
    risk_flags: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    needs_confirmation: bool = True


__all__ = [
    "AssertionPredicate",
    "ExpectedOutcome",
    "OutcomeOrigin",
    "TaskIntakeResult",
    "TaskIntakeSpec",
    "TaskIntakeStatus",
    "TaskIntakeValidationResult",
    "TestCase",
    "TestStep",
]
