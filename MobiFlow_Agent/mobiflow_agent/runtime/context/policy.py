from __future__ import annotations

from pydantic import Field

from mobiflow_agent.common.contracts import StrictModel


class ContextCompressionPolicy(StrictModel):
    max_recent_step_summaries: int = Field(default=3, ge=1)
    max_memory_items: int = Field(default=6, ge=1)
    max_evaluation_items: int = Field(default=6, ge=1)
    max_list_items: int = Field(default=6, ge=1)
    max_dict_items: int = Field(default=8, ge=1)
    max_string_chars: int = Field(default=280, ge=16)
    minimum_compaction_ratio: float = Field(default=0.85, gt=0.0, le=1.0)


__all__ = ["ContextCompressionPolicy"]
