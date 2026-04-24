from __future__ import annotations

from enum import Enum

from pydantic import Field, model_validator

from mobiflow_agent.common.contracts import (
    EntityKind,
    ExecutionProposal,
    ObservationView,
    StrictModel,
    TaskContract,
    VerificationSpec,
    VerificationVerdict,
)
from mobiflow_agent.platform.types import PlatformEntityRefs, ToolAuditRef
from mobiflow_agent.platform.types import RunGovernanceSnapshot, RunLineageSnapshot


class RuntimeLifecycle(str, Enum):
    DRAFTING = "drafting"
    OBSERVING = "observing"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    BLOCKED = "blocked"


class ConfirmationState(str, Enum):
    NONE = "none"
    REQUIRED = "required"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class CallerContext(StrictModel):
    session_id: str = Field(min_length=1)
    agent_task_id: str = Field(min_length=1)
    turn_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)


class PendingExecution(StrictModel):
    proposal: ExecutionProposal
    caller_context: CallerContext
    confirmation_state: ConfirmationState = ConfirmationState.NONE
    confirmation_id: str | None = None
    confirmation_summary: str | None = None
    confirmation_expires_at: int | None = Field(default=None, ge=0)
    audit: ToolAuditRef | None = None
    entity_refs: PlatformEntityRefs | None = None


class RecoveryExecutionContext(StrictModel):
    run_target_id: str = Field(min_length=1)
    source_run_id: str = Field(min_length=1)
    action_name: str = Field(min_length=1)
    recommended_action: str = Field(min_length=1)
    proposal_id: str = Field(min_length=1)
    expected_device_id: str | None = None
    created_run_id: str | None = None


class RecoveryObservationResult(StrictModel):
    source_governance: RunGovernanceSnapshot | None = None
    source_lineage: RunLineageSnapshot | None = None
    created_governance: RunGovernanceSnapshot | None = None
    created_lineage: RunLineageSnapshot | None = None


class AgentRuntimeState(StrictModel):
    session_id: str = Field(min_length=1)
    lifecycle: RuntimeLifecycle = RuntimeLifecycle.DRAFTING
    turn_index: int = Field(default=0, ge=0)
    step_index: int = Field(default=0, ge=0)
    active_contract: TaskContract | None = None
    focus_kind: EntityKind | None = None
    focus_id: str | None = None
    latest_observation: ObservationView | None = None
    pending_execution: PendingExecution | None = None
    recovery_execution: RecoveryExecutionContext | None = None
    recovery_observation: RecoveryObservationResult | None = None
    recovery_summary: str | None = None
    active_verification: VerificationSpec | None = None
    latest_verdict: VerificationVerdict | None = None
    known_resource_handles: list[str] = Field(default_factory=list)
    audit_refs: list[ToolAuditRef] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_runtime_state(self) -> "AgentRuntimeState":
        if self.lifecycle == RuntimeLifecycle.AWAITING_APPROVAL and self.pending_execution is None:
            raise ValueError("AgentRuntimeState awaiting approval requires pending execution.")
        if self.lifecycle == RuntimeLifecycle.VERIFYING and self.active_verification is None:
            raise ValueError("AgentRuntimeState verifying requires an active verification spec.")
        if self.focus_id and self.focus_kind is None:
            raise ValueError("AgentRuntimeState focus_id requires focus_kind.")
        return self
