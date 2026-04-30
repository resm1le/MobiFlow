from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    """Common base model for canonical contracts."""

    model_config = ConfigDict(extra="forbid")


class EntityKind(str, Enum):
    RUN = "run"
    RUN_TARGET = "run_target"
    TASK = "task"
    ATTEMPT = "attempt"
    DEVICE = "device"
    DEVICE_POOL = "device_pool"


class ApprovalMode(str, Enum):
    NEVER = "never"
    ON_RISK = "on_risk"
    ALWAYS = "always"


class ObservationFactSource(str, Enum):
    PLATFORM = "platform"
    EXECUTOR = "executor"
    USER = "user"
    AGENT = "agent"


class EvidenceKind(str, Enum):
    PLATFORM_SNAPSHOT = "platform_snapshot"
    EVENT = "event"
    ARTIFACT = "artifact"
    AUDIT = "audit"
    USER_CONFIRMATION = "user_confirmation"
    INLINE_NOTE = "inline_note"


class VerificationStatus(str, Enum):
    VERIFIED_SUCCESS = "verified_success"
    VERIFIED_FAILED = "verified_failed"
    VERIFIED_UNKNOWN = "verified_unknown"
    BLOCKED = "blocked"


class TaskConstraint(StrictModel):
    key: str = Field(min_length=1)
    description: str = Field(min_length=1)
    source: str | None = None
    required: bool = True


class SuccessCriterion(StrictModel):
    criterion_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    evidence_hint: str | None = None


class TaskContract(StrictModel):
    contract_id: str = Field(min_length=1)
    user_goal: str = Field(min_length=1)
    outcome: str = Field(min_length=1)
    target_kind: EntityKind | None = None
    target_id: str | None = None
    constraints: list[TaskConstraint] = Field(default_factory=list)
    success_criteria: list[SuccessCriterion] = Field(default_factory=list)
    verification_focus: list[str] = Field(default_factory=list)
    approval_mode: ApprovalMode = ApprovalMode.ON_RISK

    @model_validator(mode="after")
    def validate_contract(self) -> "TaskContract":
        if not self.success_criteria:
            raise ValueError("TaskContract requires at least one success criterion.")
        return self


class EvidenceRef(StrictModel):
    evidence_id: str = Field(min_length=1)
    kind: EvidenceKind
    summary: str = Field(min_length=1)
    locator: str | None = None
    handle: str | None = None
    uri: str | None = None

    @model_validator(mode="after")
    def validate_locator(self) -> "EvidenceRef":
        if not any((self.locator, self.handle, self.uri)):
            raise ValueError("EvidenceRef requires a locator, handle, or uri.")
        return self


class ObservationFact(StrictModel):
    fact_id: str = Field(min_length=1)
    source: ObservationFactSource
    title: str = Field(min_length=1)
    value: Any
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)


class ObservationInference(StrictModel):
    inference_id: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    based_on_fact_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class ObservationView(StrictModel):
    observation_id: str = Field(min_length=1)
    focus_kind: EntityKind
    focus_id: str = Field(min_length=1)
    facts: list[ObservationFact] = Field(default_factory=list)
    inferences: list[ObservationInference] = Field(default_factory=list)
    resource_handles: list[str] = Field(default_factory=list)
    observed_at_ms: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_inference_links(self) -> "ObservationView":
        fact_ids = {fact.fact_id for fact in self.facts}
        if len(fact_ids) != len(self.facts):
            raise ValueError("ObservationView fact_id values must be unique.")
        for inference in self.inferences:
            unknown = [fact_id for fact_id in inference.based_on_fact_ids if fact_id not in fact_ids]
            if unknown:
                raise ValueError(
                    f"ObservationInference references unknown fact ids: {', '.join(sorted(unknown))}."
                )
        return self


class ExecutionProposal(StrictModel):
    proposal_id: str = Field(min_length=1)
    action_tool_name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    target_kind: EntityKind | None = None
    target_id: str | None = None
    rationale: str = Field(min_length=1)
    preconditions: dict[str, Any] = Field(default_factory=dict)
    expected_observation_changes: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_proposal(self) -> "ExecutionProposal":
        if self.action_tool_name == "propose_governed_action":
            raise ValueError("ExecutionProposal must name the underlying governed action tool.")
        if not self.arguments:
            raise ValueError("ExecutionProposal requires action arguments.")
        return self


class VerificationCheck(StrictModel):
    check_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    evidence_hint: str | None = None
    predicates: list["VerificationPredicate"] = Field(default_factory=list)
    required: bool = True


class VerificationPredicateOperator(str, Enum):
    EXISTS = "exists"
    EQUALS = "equals"
    CONTAINS = "contains"
    ANY_EQUALS = "any_equals"
    ANY_CONTAINS = "any_contains"


class VerificationPredicate(StrictModel):
    field_path: str = Field(min_length=1)
    operator: VerificationPredicateOperator = VerificationPredicateOperator.EQUALS
    expected: Any | None = None
    fact_id: str | None = None
    case_sensitive: bool = False


class VerificationSpec(StrictModel):
    verification_id: str = Field(min_length=1)
    target_kind: EntityKind
    target_id: str = Field(min_length=1)
    success_checks: list[VerificationCheck] = Field(default_factory=list)
    blocked_checks: list[VerificationCheck] = Field(default_factory=list)
    blocked_conditions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_checks(self) -> "VerificationSpec":
        if not self.success_checks:
            raise ValueError("VerificationSpec requires at least one success check.")
        return self


class VerificationVerdict(StrictModel):
    verdict_id: str = Field(min_length=1)
    status: VerificationStatus
    summary: str = Field(min_length=1)
    target_kind: EntityKind
    target_id: str = Field(min_length=1)
    matched_check_ids: list[str] = Field(default_factory=list)
    unmatched_check_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    blocked_reason: str | None = None
    diagnostics: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_verdict(self) -> "VerificationVerdict":
        if self.status in {VerificationStatus.VERIFIED_SUCCESS, VerificationStatus.VERIFIED_FAILED}:
            if not self.evidence_refs:
                raise ValueError("VerificationVerdict requires evidence for verified results.")
        if self.status == VerificationStatus.BLOCKED and not self.blocked_reason:
            raise ValueError("VerificationVerdict requires a blocked reason when status is blocked.")
        return self


__all__ = [
    "ApprovalMode",
    "EntityKind",
    "EvidenceKind",
    "EvidenceRef",
    "ExecutionProposal",
    "ObservationFact",
    "ObservationFactSource",
    "ObservationInference",
    "ObservationView",
    "StrictModel",
    "SuccessCriterion",
    "TaskConstraint",
    "TaskContract",
    "VerificationCheck",
    "VerificationPredicate",
    "VerificationPredicateOperator",
    "VerificationSpec",
    "VerificationStatus",
    "VerificationVerdict",
]
