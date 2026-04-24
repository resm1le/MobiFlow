from __future__ import annotations

from typing import Any

from pydantic import Field

from mobiflow_agent.common.contracts import EntityKind, StrictModel


class StepContextSummary(StrictModel):
    step_id: str = Field(min_length=1)
    step_kind: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    outcome_status: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    blocked_reason: str | None = None
    matched_check_ids: list[str] = Field(default_factory=list)
    evidence_ref_ids: list[str] = Field(default_factory=list)


class SessionContextDigest(StrictModel):
    summary: str = Field(min_length=1)
    recent_step_summaries: list[StepContextSummary] = Field(default_factory=list)
    historical_summary: str | None = None
    pending_approval_summary: str | None = None
    recovery_summary: str | None = None
    open_risks: list[str] = Field(default_factory=list)
    memory_highlights: dict[str, Any] = Field(default_factory=dict)
    evaluation_highlights: dict[str, Any] = Field(default_factory=dict)
    context_token_estimate: int = Field(default=0, ge=0)


class ContextHandoff(StrictModel):
    source_session_id: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    target_kind: EntityKind | None = None
    target_id: str | None = None
    session_digest: SessionContextDigest
    latest_verdict_summary: str | None = None
    resume_hint: str = Field(min_length=1)
    created_at: int = Field(ge=0)


class ContextCompressionResult(StrictModel):
    user_prompt: str = Field(min_length=1)
    context_payload: dict[str, Any] = Field(default_factory=dict)
    compacted: bool = False
    estimated_input_tokens_before: int = Field(default=0, ge=0)
    estimated_input_tokens_after: int = Field(default=0, ge=0)
    used_summary_profile: str | None = None
    used_imported_handoff: bool = False


__all__ = [
    "ContextCompressionResult",
    "ContextHandoff",
    "SessionContextDigest",
    "StepContextSummary",
]
