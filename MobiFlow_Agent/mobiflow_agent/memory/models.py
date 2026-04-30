from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import Field

from mobiflow_agent.common.contracts import EntityKind, StrictModel, VerificationStatus
from mobiflow_agent.task.plan import TaskStepKind


class TaskMemoryRecordKind(str, Enum):
    PLANNING_PATTERN = "planning_pattern"
    RECOVERY_PATTERN = "recovery_pattern"
    VERIFICATION_PATTERN = "verification_pattern"
    TASK_OUTCOME = "task_outcome"
    SCENARIO_OUTCOME = "scenario_outcome"


class TaskMemoryRetrievalChannel(str, Enum):
    DETERMINISTIC = "deterministic"
    VECTOR = "vector"
    HYBRID = "hybrid"
    NONE = "none"


class TaskMemoryRecordStatus(str, Enum):
    ACTIVE = "active"
    DISABLED = "disabled"
    QUARANTINED = "quarantined"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"


class TaskMemoryRecord(StrictModel):
    memory_id: str = Field(min_length=1)
    kind: TaskMemoryRecordKind
    source: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    target_kind: EntityKind | None = None
    target_id: str | None = None
    step_kind: TaskStepKind | None = None
    role_scope: str | None = None
    verdict_status: VerificationStatus | None = None
    blocked_reason: str | None = None
    summary: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    evidence_ref_ids: list[str] = Field(default_factory=list)
    proposal_fingerprint: str | None = None
    content_payload: dict[str, Any] = Field(default_factory=dict)
    created_at_ms: int = Field(ge=0)
    updated_at_ms: int = Field(ge=0)
    status: TaskMemoryRecordStatus = TaskMemoryRecordStatus.ACTIVE
    version: int = Field(default=1, ge=1)
    expires_at_ms: int | None = Field(default=None, ge=0)
    superseded_by: str | None = None
    last_accessed_at_ms: int | None = Field(default=None, ge=0)
    access_count: int = Field(default=0, ge=0)
    quality_decision: str | None = None
    governance_tags: list[str] = Field(default_factory=list)


class TaskMemoryQuery(StrictModel):
    role_scope: str | None = None
    step_kind: TaskStepKind | None = None
    kinds: list[TaskMemoryRecordKind] = Field(default_factory=list)
    goal_text: str | None = None
    target_kind: EntityKind | None = None
    target_id: str | None = None
    verdict_statuses: list[VerificationStatus] = Field(default_factory=list)
    blocked_reason: str | None = None
    tags: list[str] = Field(default_factory=list)
    top_k: int = Field(default=5, ge=1)
    semantic_query_text: str | None = None
    applicability_context: dict[str, Any] = Field(default_factory=dict)
    min_score: float = Field(default=0.0, ge=0.0)
    statuses: list[TaskMemoryRecordStatus] = Field(default_factory=list)
    include_expired: bool = False


class TaskMemoryMatch(StrictModel):
    record: TaskMemoryRecord
    score: float = Field(ge=0.0)
    channel: TaskMemoryRetrievalChannel
    matched_terms: list[str] = Field(default_factory=list)
    summary: str = Field(min_length=1)


class TaskMemoryRetrievalResult(StrictModel):
    query: TaskMemoryQuery
    channel: TaskMemoryRetrievalChannel
    matches: list[TaskMemoryMatch] = Field(default_factory=list)
    summary: str = Field(min_length=1)


class TaskMemoryWritebackRequest(StrictModel):
    session_id: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    source: str = Field(min_length=1)
    records: list[TaskMemoryRecord] = Field(default_factory=list)


class TaskMemoryWritebackResult(StrictModel):
    session_id: str = Field(min_length=1)
    stored_records: list[TaskMemoryRecord] = Field(default_factory=list)
    rejected_records: list[TaskMemoryRecord] = Field(default_factory=list)
    skipped_record_kinds: list[TaskMemoryRecordKind] = Field(default_factory=list)
    created_count: int = Field(default=0, ge=0)
    updated_count: int = Field(default=0, ge=0)
    rejected_count: int = Field(default=0, ge=0)
    quarantined_count: int = Field(default=0, ge=0)
    superseded_count: int = Field(default=0, ge=0)
    expired_count: int = Field(default=0, ge=0)
    quality_issue_summaries: list[str] = Field(default_factory=list)
    governance_issue_summaries: list[str] = Field(default_factory=list)
    summary: str = Field(min_length=1)


class TaskMemoryContext(StrictModel):
    role_scope: str = Field(min_length=1)
    query: TaskMemoryQuery
    channel: TaskMemoryRetrievalChannel
    matches: list[TaskMemoryMatch] = Field(default_factory=list)
    highlights: list[dict[str, Any]] = Field(default_factory=list)
    summary: str = Field(min_length=1)
    retrieval_token_estimate: int | None = Field(default=None, ge=0)


class TaskMemoryPolicy(StrictModel):
    planner_top_k: int = Field(default=4, ge=1)
    recovery_top_k: int = Field(default=4, ge=1)
    verifier_top_k: int = Field(default=5, ge=1)
    deterministic_weight: float = Field(default=1.0, ge=0.0)
    vector_weight: float = Field(default=1.0, ge=0.0)
    min_score: float = Field(default=0.25, ge=0.0)
    writeback_enabled: bool = True
    writeback_kinds: list[TaskMemoryRecordKind] = Field(
        default_factory=lambda: [
            TaskMemoryRecordKind.PLANNING_PATTERN,
            TaskMemoryRecordKind.RECOVERY_PATTERN,
            TaskMemoryRecordKind.VERIFICATION_PATTERN,
            TaskMemoryRecordKind.TASK_OUTCOME,
        ]
    )
    max_highlights: int = Field(default=4, ge=1)
    dedupe_by_fingerprint: bool = True
    max_records_per_session: int = Field(default=4, ge=1)
    max_payload_chars: int = Field(default=4000, ge=256)
    allow_unknown_writeback: bool = False
    require_evidence_for_writeback: bool = True
    quality_fail_action: str = Field(default="reject", min_length=1)


class TaskMemoryEmbeddingEntry(StrictModel):
    memory_id: str = Field(min_length=1)
    profile_name: str = Field(min_length=1)
    vector: list[float] = Field(default_factory=list)
    source_text: str = Field(min_length=1)
    updated_at_ms: int = Field(ge=0)


__all__ = [
    "TaskMemoryContext",
    "TaskMemoryEmbeddingEntry",
    "TaskMemoryMatch",
    "TaskMemoryPolicy",
    "TaskMemoryQuery",
    "TaskMemoryRecord",
    "TaskMemoryRecordKind",
    "TaskMemoryRecordStatus",
    "TaskMemoryRetrievalChannel",
    "TaskMemoryRetrievalResult",
    "TaskMemoryWritebackRequest",
    "TaskMemoryWritebackResult",
]
