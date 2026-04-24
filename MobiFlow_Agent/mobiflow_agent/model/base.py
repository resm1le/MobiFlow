from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from pydantic import Field, TypeAdapter

from mobiflow_agent.common.contracts import StrictModel
from mobiflow_agent.model.telemetry import ModelInvocationTrace

T = TypeVar("T")


class ModelError(RuntimeError):
    def __init__(self, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class ModelMessage(StrictModel):
    role: str = Field(min_length=1)
    content: str = Field(min_length=1)


class ModelRequest(StrictModel):
    invocation_id: str = Field(min_length=1)
    profile_name: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    messages: list[ModelMessage] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    timeout_ms: int | None = Field(default=None, ge=1)
    max_retries: int = Field(default=0, ge=0)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_output_tokens: int | None = Field(default=None, ge=1)


class ModelResponse(StrictModel):
    invocation_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    output_text: str = ""
    structured_output: Any | None = None
    trace: ModelInvocationTrace


class EmbeddingRequest(StrictModel):
    invocation_id: str = Field(min_length=1)
    profile_name: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    input_text: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    timeout_ms: int | None = Field(default=None, ge=1)
    max_retries: int = Field(default=0, ge=0)


class EmbeddingResponse(StrictModel):
    invocation_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    vector: list[float] = Field(default_factory=list)
    trace: ModelInvocationTrace


@dataclass(slots=True)
class StructuredGenerationRequest:
    request: ModelRequest
    response_model: type[T]


@dataclass(slots=True)
class StructuredGenerationResult:
    output: T
    response: ModelResponse


class StructuredModelSupport:
    @staticmethod
    def validate_structured_output(response: ModelResponse, response_model: type[T]) -> T:
        payload = response.structured_output
        if payload is None:
            if not response.output_text.strip():
                raise ModelError("EMPTY_RESPONSE", "Model response did not contain structured output.")
            try:
                payload = json.loads(response.output_text)
            except json.JSONDecodeError as exc:
                raise ModelError("INVALID_JSON", "Model response was not valid JSON.") from exc
        try:
            return TypeAdapter(response_model).validate_python(payload)
        except Exception as exc:
            raise ModelError("SCHEMA_VALIDATION_FAILED", "Model response failed schema validation.") from exc


class ModelClient(Protocol):
    def generate(self, request: ModelRequest) -> ModelResponse:
        """Generate a raw response for the supplied request."""

    def generate_structured(self, request: StructuredGenerationRequest) -> StructuredGenerationResult:
        """Generate and validate a structured response for the supplied request."""


class EmbeddingClient(Protocol):
    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Generate an embedding vector for the supplied request."""


__all__ = [
    "EmbeddingClient",
    "EmbeddingRequest",
    "EmbeddingResponse",
    "ModelClient",
    "ModelError",
    "ModelMessage",
    "ModelRequest",
    "ModelResponse",
    "StructuredGenerationRequest",
    "StructuredGenerationResult",
    "StructuredModelSupport",
]
