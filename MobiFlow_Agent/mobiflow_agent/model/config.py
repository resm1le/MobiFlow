from __future__ import annotations

from pydantic import Field

from mobiflow_agent.agents.contracts import AgentRole
from mobiflow_agent.common.contracts import StrictModel


class ModelSettings(StrictModel):
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_output_tokens: int | None = Field(default=None, ge=1)
    input_token_budget: int | None = Field(default=None, ge=1)
    compaction_target_tokens: int | None = Field(default=None, ge=1)
    timeout_ms: int = Field(default=30000, ge=1)
    max_retries: int = Field(default=0, ge=0)
    fallback_profile: str | None = None
    summary_profile: str | None = None


class ModelProfile(StrictModel):
    name: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    settings: ModelSettings = Field(default_factory=ModelSettings)
    metadata: dict[str, str] = Field(default_factory=dict)


class EmbeddingProfile(StrictModel):
    name: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    timeout_ms: int = Field(default=30000, ge=1)
    max_retries: int = Field(default=0, ge=0)
    metadata: dict[str, str] = Field(default_factory=dict)


class RoleModelPolicy(StrictModel):
    default_profile: str | None = None
    role_profiles: dict[str, str] = Field(default_factory=dict)

    def resolve(self, role: AgentRole | str) -> str | None:
        role_name = role.value if isinstance(role, AgentRole) else role
        return self.role_profiles.get(role_name, self.default_profile)

__all__ = ["EmbeddingProfile", "ModelProfile", "ModelSettings", "RoleModelPolicy"]
