"""Provider-agnostic model subsystem for model-driven task roles."""

from importlib import import_module

from mobiflow_agent.model.base import (
    EmbeddingClient,
    EmbeddingRequest,
    EmbeddingResponse,
    ModelClient,
    ModelError,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)
from mobiflow_agent.model.bootstrap import ModelRegistryBuilder
from mobiflow_agent.model.config import EmbeddingProfile, ModelProfile, ModelSettings, RoleModelPolicy
from mobiflow_agent.model.runtime import ModelRegistry, ModelRuntime
from mobiflow_agent.model.telemetry import ModelInvocationTrace

__all__ = [
    "EmbeddingClient",
    "EmbeddingProfile",
    "EmbeddingRequest",
    "EmbeddingResponse",
    "ModelClient",
    "ModelError",
    "ModelInvocationTrace",
    "ModelMessage",
    "ModelProfile",
    "ModelRegistry",
    "ModelRegistryBuilder",
    "ModelRequest",
    "ModelResponse",
    "ModelRuntime",
    "ModelSettings",
    "OpenAICompatibleProviderConfig",
    "PlannerPromptBuilder",
    "RecoveryPromptBuilder",
    "RoleModelPolicy",
    "StructuredGenerationRequest",
    "StructuredGenerationResult",
    "VerifierPromptBuilder",
]


def __getattr__(name: str):
    if name in {"PlannerPromptBuilder", "RecoveryPromptBuilder", "VerifierPromptBuilder"}:
        module = import_module("mobiflow_agent.model.prompting")
        return getattr(module, name)
    if name == "OpenAICompatibleProviderConfig":
        module = import_module("mobiflow_agent.model.providers")
        return getattr(module, name)
    raise AttributeError(f"module 'mobiflow_agent.model' has no attribute {name!r}")
