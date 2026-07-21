from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import Field

from mobiflow_agent.common.contracts import StrictModel


class ToolRiskLevel(str, Enum):
    DISCOVERY = "discovery"
    ADVISORY = "advisory"
    EXECUTION = "execution"


class FailureCategory(str, Enum):
    PROFILE_NOT_READY = "PROFILE_NOT_READY"
    UI_NOT_FOUND = "UI_NOT_FOUND"
    NETWORK_ERROR = "NETWORK_ERROR"
    PERMISSION_MISSING = "PERMISSION_MISSING"
    DEVICE_STATE_MISMATCH = "DEVICE_STATE_MISMATCH"
    LEASE_INTERRUPTED = "LEASE_INTERRUPTED"
    PRECHECK_FAILED = "PRECHECK_FAILED"
    QUEUE_TIMEOUT = "QUEUE_TIMEOUT"
    RUN_CANCELLED = "RUN_CANCELLED"
    UNKNOWN = "UNKNOWN"


class RetryRecommendation(str, Enum):
    NO_RETRY = "NO_RETRY"
    RETRY_SAME_DEVICE = "RETRY_SAME_DEVICE"
    RETRY_OTHER_DEVICE = "RETRY_OTHER_DEVICE"
    INSPECT_PROFILE = "INSPECT_PROFILE"
    INSPECT_ENVIRONMENT = "INSPECT_ENVIRONMENT"
    ESCALATE_OPERATOR = "ESCALATE_OPERATOR"


class SuggestedNextAction(str, Enum):
    NONE = "NONE"
    RETRY_TARGET = "RETRY_TARGET"
    RETRY_ON_OTHER_DEVICE = "RETRY_ON_OTHER_DEVICE"
    INSPECT_ARTIFACTS = "INSPECT_ARTIFACTS"
    INSPECT_DEVICE_HEALTH = "INSPECT_DEVICE_HEALTH"
    INSPECT_PROFILE_LOGIC = "INSPECT_PROFILE_LOGIC"
    CHECK_CONTROL_PLANE = "CHECK_CONTROL_PLANE"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class ToolExecutionError(StrictModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    retryable: bool = False


class ToolAuditRef(StrictModel):
    audit_id: str = Field(min_length=1)
    risk_level: ToolRiskLevel


class PlatformEntityRefs(StrictModel):
    proposal_id: str | None = None
    run_id: str | None = None
    run_target_id: str | None = None
    task_id: str | None = None
    attempt_id: str | None = None
    artifact_ids: list[str] = Field(default_factory=list)


class ToolCatalogItem(StrictModel):
    name: str = Field(min_length=1)
    title: str | None = None
    description: str | None = None
    tool_kind: str = Field(min_length=1)
    risk_level: ToolRiskLevel
    requires_approval: bool
    confirmation_mode: str | None = None
    input_schema: dict[str, Any] = Field(default_factory=dict)
    semantic_tags: list[str] = Field(default_factory=list)


class DispatchDeviceContext(StrictModel):
    device_id: str = Field(min_length=1)
    installed_profiles: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    host_group: str | None = None
    registered: bool
    online: bool
    busy: bool
    status: str = Field(min_length=1)
    updated_at: int = Field(ge=0)


class AvailableDevicePoolContext(StrictModel):
    pool_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    host_group: str | None = None
    device_count: int = Field(ge=0)
    required_tags: list[str] = Field(default_factory=list)
    excluded_tags: list[str] = Field(default_factory=list)


class AvailableProfileContext(StrictModel):
    profile_package: str = Field(min_length=1)
    installed_device_count: int = Field(ge=0)
    supported_task_types: list[str] = Field(default_factory=list)
    required_task_payload_fields: list[str] = Field(default_factory=list)
    recommended_defaults: dict[str, Any] = Field(default_factory=dict)
    known_limitations: list[str] = Field(default_factory=list)


class PlatformRunConfig(StrictModel):
    loop_count: int = Field(ge=0)
    budget_ms: int = Field(ge=0)
    loop_interval_ms: int = Field(ge=0)
    network_isolation_enabled: bool
    poll_interval_ms: int = Field(ge=0)
    heartbeat_interval_ms: int = Field(ge=0)


class PlatformArtifactPolicy(StrictModel):
    upload_log: bool
    upload_screenshot: bool
    upload_dump: bool


class RunPlanningDefaultPolicy(StrictModel):
    priority: int
    max_retries_per_device: int = Field(ge=0)
    queue_timeout_ms: int = Field(ge=0)
    default_run_config: PlatformRunConfig
    default_artifact_policy: PlatformArtifactPolicy


class RunPlanningCatalogContext(StrictModel):
    available_device_pools: list[AvailableDevicePoolContext] = Field(default_factory=list)
    available_profiles: list[AvailableProfileContext] = Field(default_factory=list)
    default_run_policy: RunPlanningDefaultPolicy
    allowed_task_types: list[str] = Field(default_factory=list)


class RunCounts(StrictModel):
    total_targets: int = Field(ge=0)
    queued: int = Field(ge=0)
    running: int = Field(ge=0)
    retry_pending: int = Field(ge=0)
    succeeded: int = Field(ge=0)
    failed: int = Field(ge=0)
    cancelled: int = Field(ge=0)


class RunAttemptCounts(StrictModel):
    total: int = Field(ge=0)
    running: int = Field(ge=0)
    failed: int = Field(ge=0)
    succeeded: int = Field(ge=0)


class RunSummaryContext(StrictModel):
    run_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str | None = None
    pool_id: str | None = None
    status: str = Field(min_length=1)
    final_state: str | None = None
    task_type: str = Field(min_length=1)
    profile_package: str | None = Field(default=None, min_length=1)
    priority: int | None = None
    labels: list[str] = Field(default_factory=list)
    source: str | None = None
    created_by: str | None = None
    max_retries_per_device: int | None = None
    queue_timeout_ms: int | None = None
    cancel_requested: bool
    created_at: int | None = Field(default=None, ge=0)
    updated_at: int | None = Field(default=None, ge=0)
    started_at: int | None = Field(default=None, ge=0)
    finished_at: int | None = Field(default=None, ge=0)
    counts: RunCounts


class AttemptContext(StrictModel):
    attempt_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    device_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    status: str = Field(min_length=1)
    final_state: str | None = None
    failure_reason: str | None = None
    started_at: int | None = Field(default=None, ge=0)
    finished_at: int | None = Field(default=None, ge=0)
    created_at: int | None = Field(default=None, ge=0)
    updated_at: int | None = Field(default=None, ge=0)


class RunTargetContext(StrictModel):
    run_target_id: str = Field(min_length=1)
    device_id: str = Field(min_length=1)
    sequence_id: str | None = Field(default=None, min_length=1)
    status: str = Field(min_length=1)
    attempt_count: int = Field(ge=0)
    current_task_id: str | None = None
    latest_attempt_id: str | None = None
    failure_reason: str | None = None
    started_at: int | None = Field(default=None, ge=0)
    finished_at: int | None = Field(default=None, ge=0)
    latest_attempt: AttemptContext | None = None


class FailureTriageValidation(StrictModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class FailureTriageRecord(StrictModel):
    triage_result_id: str = Field(min_length=1)
    run_target_id: str = Field(min_length=1)
    failure_category: FailureCategory
    probable_cause: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    retry_recommendation: RetryRecommendation
    suggested_next_action: SuggestedNextAction
    operator_review_hints: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    validation: FailureTriageValidation
    model_meta: dict[str, Any] = Field(default_factory=dict)
    generated_at: int = Field(ge=0)


class RecoveryGuidance(StrictModel):
    entity_kind: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    allowed_actions: list[str] = Field(default_factory=list)
    recommended_action: str = Field(min_length=1)
    requires_approval: bool
    required_inputs: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)
    stop_conditions: list[str] = Field(default_factory=list)
    stop_conditions_summary: str = Field(min_length=1)
    why_not_others: str = Field(min_length=1)
    explanation: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


class GovernedActionState(str, Enum):
    APPROVAL_REQUIRED = "approval_required"
    EXECUTED = "executed"
    FAILED = "failed"


class GovernedActionResult(StrictModel):
    state: GovernedActionState
    proposal_id: str = Field(min_length=1)
    action_tool_name: str = Field(min_length=1)
    audit: ToolAuditRef | None = None
    entity_refs: PlatformEntityRefs | None = None
    confirmation_id: str | None = None
    confirmation_summary: str | None = None
    confirmation_expires_at: int | None = Field(default=None, ge=0)
    result: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    error: ToolExecutionError | None = None


class AuditTimelineEntry(StrictModel):
    audit: ToolAuditRef
    request_id: str | None = None
    session_id: str | None = None
    tool: str = Field(min_length=1)
    status: str = Field(min_length=1)
    caller_context: dict[str, str | None] = Field(default_factory=dict)
    entity_refs: PlatformEntityRefs = Field(default_factory=PlatformEntityRefs)
    created_at: int = Field(ge=0)
    updated_at: int = Field(ge=0)


class AttemptArtifactResource(StrictModel):
    artifact_id: str = Field(min_length=1)
    attempt_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    artifact_type: str = Field(min_length=1)
    file_name: str = Field(min_length=1)
    mime_type: str | None = None
    size_bytes: int | None = Field(default=None, ge=0)
    created_at: int = Field(ge=0)
    resource_handle: str | None = None


class RunDetailContext(StrictModel):
    run: RunSummaryContext
    task_payload: dict[str, Any] = Field(default_factory=dict)
    run_config: dict[str, Any] = Field(default_factory=dict)
    artifact_policy: dict[str, Any] = Field(default_factory=dict)
    targets: list[RunTargetContext] = Field(default_factory=list)


class RunGovernanceSnapshot(StrictModel):
    run_id: str = Field(min_length=1)
    status: str = Field(min_length=1)
    target_counts: RunCounts
    attempt_counts: RunAttemptCounts
    latest_attempt_ids: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    last_updated_at: int = Field(ge=0)


class RunLineageSnapshot(StrictModel):
    run_id: str = Field(min_length=1)
    run: RunDetailContext
    targets: list[RunTargetContext] = Field(default_factory=list)
    attempts: list[AttemptContext] = Field(default_factory=list)
    latest_artifacts: list[AttemptArtifactResource] = Field(default_factory=list)
    audit_refs: list[AuditTimelineEntry] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    current_governed_options: list[str] = Field(default_factory=list)
