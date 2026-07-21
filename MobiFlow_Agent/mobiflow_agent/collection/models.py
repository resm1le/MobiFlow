from __future__ import annotations

from enum import Enum

from pydantic import Field, field_validator, model_validator

from mobiflow_agent.common.contracts import ExecutionProposal, StrictModel
from mobiflow_agent.platform.types import GovernedActionResult, GovernedActionState
from mobiflow_agent.waypoint.catalog import SEQUENCE_ID_PATTERN


class CollectionDispatchStatus(str, Enum):
    NEEDS_CLARIFICATION = "needs_clarification"
    REJECTED = "rejected"
    ERROR = "error"
    PLANNED = "planned"
    APPROVAL_REQUIRED = "approval_required"
    EXECUTED = "executed"
    FAILED = "failed"


class CollectionIntent(StrictModel):
    raw_text: str = Field(min_length=1)
    task_type: str = Field(default="PLUGIN_RUN", min_length=1)
    labels: list[str] = Field(default_factory=list)

    @field_validator("raw_text", "task_type")
    @classmethod
    def require_non_blank_text(cls, value: str) -> str:
        return _require_non_blank(value, "Collection intent text fields must not be blank.")

    @field_validator("labels")
    @classmethod
    def validate_labels(cls, values: list[str]) -> list[str]:
        return _validate_unique_non_blank(values, "labels")


class ExplicitDeviceSelector(StrictModel):
    device_ids: list[str] = Field(min_length=1)

    @field_validator("device_ids")
    @classmethod
    def validate_device_ids(cls, values: list[str]) -> list[str]:
        return _validate_unique_non_blank(values, "device_ids")


class TaggedDeviceSelector(StrictModel):
    count: int = Field(gt=0)
    required_tags: list[str] = Field(default_factory=list)
    excluded_tags: list[str] = Field(default_factory=list)

    @field_validator("required_tags", "excluded_tags")
    @classmethod
    def validate_tags(cls, values: list[str], info) -> list[str]:
        return _validate_unique_non_blank(values, info.field_name)

    @model_validator(mode="after")
    def validate_tag_sets(self) -> "TaggedDeviceSelector":
        overlap = set(self.required_tags) & set(self.excluded_tags)
        if overlap:
            raise ValueError(
                "required_tags and excluded_tags must not overlap: "
                + ", ".join(sorted(overlap))
            )
        return self


DeviceSelector = ExplicitDeviceSelector | TaggedDeviceSelector


class DispatchEntry(StrictModel):
    sequence_id: str = Field(min_length=1)
    select: DeviceSelector

    @field_validator("sequence_id")
    @classmethod
    def require_versioned_sequence_id(cls, value: str) -> str:
        if not SEQUENCE_ID_PATTERN.fullmatch(value):
            raise ValueError("sequence_id must be a lowercase, explicit .vN identifier.")
        return value


class DispatchPlan(StrictModel):
    name: str = Field(min_length=1)
    description: str | None = None
    dispatch: list[DispatchEntry] = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _require_non_blank(value, "Dispatch plan name must not be blank.")

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _require_non_blank(value, "Dispatch plan description must not be blank.")


class IntentPlannerDecisionType(str, Enum):
    PLAN = "plan"
    CLARIFY = "clarify"


class IntentPlannerDecision(StrictModel):
    decision_type: IntentPlannerDecisionType
    plan: DispatchPlan | None = None
    clarification_questions: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("clarification_questions")
    @classmethod
    def validate_questions(cls, values: list[str]) -> list[str]:
        return _validate_unique_non_blank(values, "clarification_questions")

    @model_validator(mode="after")
    def validate_decision(self) -> "IntentPlannerDecision":
        if self.decision_type == IntentPlannerDecisionType.PLAN:
            if self.plan is None:
                raise ValueError("PLAN decision requires a dispatch plan.")
            if self.clarification_questions:
                raise ValueError("PLAN decision cannot carry clarification questions.")
            return self
        if self.plan is not None:
            raise ValueError("CLARIFY decision cannot carry a dispatch plan.")
        if not self.clarification_questions:
            raise ValueError("CLARIFY decision requires at least one question.")
        return self


class IntentPlanningResult(StrictModel):
    status: CollectionDispatchStatus
    plan: DispatchPlan | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    issues: list[str] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)
    trace_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_planning_status(self) -> "IntentPlanningResult":
        if self.status == CollectionDispatchStatus.PLANNED:
            if self.plan is None:
                raise ValueError("PLANNED intent result requires a dispatch plan.")
            if self.clarification_questions:
                raise ValueError("PLANNED intent result cannot require clarification.")
            return self
        if self.plan is not None:
            raise ValueError("Non-PLANNED intent result cannot carry a dispatch plan.")
        if (
            self.status == CollectionDispatchStatus.NEEDS_CLARIFICATION
            and not self.clarification_questions
        ):
            raise ValueError("NEEDS_CLARIFICATION intent result requires a question.")
        return self


class DispatchCompilationResult(StrictModel):
    accepted: bool
    proposal: ExecutionProposal | None = None
    issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_proposal(self) -> "DispatchCompilationResult":
        if self.accepted and self.proposal is None:
            raise ValueError("Accepted dispatch compilation requires a proposal.")
        if not self.accepted and self.proposal is not None:
            raise ValueError("Rejected dispatch compilation cannot carry a proposal.")
        return self


class CollectionDispatchResult(StrictModel):
    status: CollectionDispatchStatus
    plan: DispatchPlan | None = None
    proposal: ExecutionProposal | None = None
    governed_result: GovernedActionResult | None = None
    issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)
    trace_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_dispatch_status(self) -> "CollectionDispatchResult":
        if self.status == CollectionDispatchStatus.PLANNED:
            if self.plan is None or self.proposal is None:
                raise ValueError("PLANNED dispatch result requires plan and proposal.")
            if self.governed_result is not None:
                raise ValueError("PLANNED dispatch result cannot carry a governed result.")
            return self

        governed_states = {
            CollectionDispatchStatus.APPROVAL_REQUIRED: GovernedActionState.APPROVAL_REQUIRED,
            CollectionDispatchStatus.EXECUTED: GovernedActionState.EXECUTED,
            CollectionDispatchStatus.FAILED: GovernedActionState.FAILED,
        }
        expected_state = governed_states.get(self.status)
        if expected_state is not None:
            if self.plan is None or self.proposal is None or self.governed_result is None:
                raise ValueError(
                    f"{self.status.value} dispatch result requires plan, proposal, and governed result."
                )
            if self.governed_result.state != expected_state:
                raise ValueError(
                    f"{self.status.value} dispatch result does not match governed state."
                )
            return self

        if self.proposal is not None or self.governed_result is not None:
            raise ValueError(
                "Non-submission dispatch results cannot carry proposal or governed result."
            )
        return self


def _require_non_blank(value: str, message: str) -> str:
    if not value.strip():
        raise ValueError(message)
    return value


def _validate_unique_non_blank(values: list[str], field_name: str) -> list[str]:
    for value in values:
        if not value.strip():
            raise ValueError(f"{field_name} values must not be blank.")
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} values must be unique.")
    return values


__all__ = [
    "CollectionDispatchResult",
    "CollectionDispatchStatus",
    "CollectionIntent",
    "DeviceSelector",
    "DispatchCompilationResult",
    "DispatchEntry",
    "DispatchPlan",
    "ExplicitDeviceSelector",
    "IntentPlannerDecision",
    "IntentPlannerDecisionType",
    "IntentPlanningResult",
    "TaggedDeviceSelector",
]
