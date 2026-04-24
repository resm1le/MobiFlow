from __future__ import annotations

from typing import Any

from pydantic import Field

from mobiflow_agent.common.contracts import StrictModel


class ModelInvocationTrace(StrictModel):
    invocation_id: str = Field(min_length=1)
    profile_name: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    role: str | None = None
    latency_ms: int = Field(default=0, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    finish_reason: str | None = None
    error_code: str | None = None
    retry_count: int = Field(default=0, ge=0)
    fallback_from_profile: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


__all__ = ["ModelInvocationTrace"]
