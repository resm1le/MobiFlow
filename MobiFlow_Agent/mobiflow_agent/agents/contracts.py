from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import Field, model_validator

from mobiflow_agent.common.contracts import EntityKind, EvidenceRef, ExecutionProposal, StrictModel, VerificationSpec
from mobiflow_agent.platform.types import RecoveryGuidance
from mobiflow_agent.runtime.state import RecoveryExecutionContext, RecoveryObservationResult


class AgentRole(str, Enum):
    PLANNER = "planner"
    OBSERVER = "observer"
    STEP_POLICY = "step_policy"
    EXECUTOR = "executor"
    VERIFIER = "verifier"
    RECOVERY = "recovery"


class StepDecisionType(str, Enum):
    OBSERVE_AGAIN = "observe_again"
    PROPOSE_EXECUTION = "propose_execution"
    STEP_SUCCEEDED = "step_succeeded"
    STEP_BLOCKED = "step_blocked"
    REQUEST_REPLAN = "request_replan"
    HANDOFF = "handoff"


class ReplanDecisionType(str, Enum):
    RETRY_CURRENT_STEP = "retry_current_step"
    SKIP_CURRENT_STEP = "skip_current_step"
    HANDOFF = "handoff"
    FAIL = "fail"


class RoleRequest(StrictModel):
    request_id: str = Field(min_length=1)
    role: AgentRole
    session_id: str = Field(min_length=1)
    step_id: str | None = None
    reason: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)


class RoleResult(StrictModel):
    result_id: str = Field(min_length=1)
    role: AgentRole
    session_id: str = Field(min_length=1)
    step_id: str | None = None
    summary: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    handoff_reason: str | None = None
    next_role: AgentRole | None = None


class StepDecision(StrictModel):
    decision_id: str = Field(min_length=1)
    decision_type: StepDecisionType
    summary: str = Field(min_length=1)
    proposal: ExecutionProposal | None = None
    blocked_reason: str | None = None

    @model_validator(mode="after")
    def validate_decision(self) -> "StepDecision":
        if self.decision_type == StepDecisionType.PROPOSE_EXECUTION and self.proposal is None:
            raise ValueError("StepDecision PROPOSE_EXECUTION requires a proposal.")
        if self.decision_type != StepDecisionType.PROPOSE_EXECUTION and self.proposal is not None:
            raise ValueError("StepDecision proposal is only allowed for PROPOSE_EXECUTION.")
        if self.decision_type in {StepDecisionType.STEP_BLOCKED, StepDecisionType.HANDOFF} and not self.blocked_reason:
            raise ValueError("StepDecision blocked/handoff decisions require blocked_reason.")
        return self


class ReplanDecision(StrictModel):
    decision_type: ReplanDecisionType
    summary: str = Field(min_length=1)


class RecoveryOutcome(StrictModel):
    summary: str = Field(min_length=1)
    target_kind: EntityKind | None = None
    target_id: str | None = None
    guidance: RecoveryGuidance | None = None
    execution_context: RecoveryExecutionContext | None = None
    observation: RecoveryObservationResult | None = None
    verification_spec: VerificationSpec | None = None
    replan_decision: ReplanDecision | None = None
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
