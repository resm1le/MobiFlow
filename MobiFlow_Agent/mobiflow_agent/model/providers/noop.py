from __future__ import annotations

import json
from hashlib import sha256
from typing import Any

from mobiflow_agent.model.base import (
    EmbeddingRequest,
    EmbeddingResponse,
    ModelError,
    ModelResponse,
    StructuredGenerationRequest,
    StructuredGenerationResult,
    StructuredModelSupport,
)
from mobiflow_agent.model.telemetry import ModelInvocationTrace


class NoopModelClient(StructuredModelSupport):
    def __init__(
        self,
        *,
        provider_name: str = "noop",
        default_model: str = "noop-model",
        responses: list[Any] | None = None,
    ):
        self._provider_name = provider_name
        self._default_model = default_model
        self._responses = list(responses or [])

    def enqueue(self, response: Any) -> None:
        self._responses.append(response)

    def generate(self, request):
        if not self._responses:
            raise ModelError("NO_NOOP_RESPONSE", "No queued noop model response was configured.")
        candidate = self._responses.pop(0)
        if isinstance(candidate, Exception):
            if isinstance(candidate, ModelError):
                raise candidate
            raise ModelError("NOOP_EXCEPTION", str(candidate)) from candidate
        if isinstance(candidate, ModelResponse):
            trace = candidate.trace.model_copy(
                update={
                    "invocation_id": request.invocation_id,
                    "profile_name": request.profile_name,
                    "provider": request.provider,
                    "model": request.model,
                    "role": request.metadata.get("role"),
                }
            )
            return candidate.model_copy(update={"trace": trace})
        if hasattr(candidate, "model_dump"):
            structured_output = candidate.model_dump(mode="python")
            output_text = json.dumps(structured_output, ensure_ascii=False)
        elif isinstance(candidate, dict):
            structured_output = candidate
            output_text = json.dumps(candidate, ensure_ascii=False)
        else:
            output_text = str(candidate)
            try:
                structured_output = json.loads(output_text)
            except json.JSONDecodeError:
                structured_output = None
        return ModelResponse(
            invocation_id=request.invocation_id,
            provider=request.provider or self._provider_name,
            model=request.model or self._default_model,
            output_text=output_text,
            structured_output=structured_output,
            trace=ModelInvocationTrace(
                invocation_id=request.invocation_id,
                profile_name=request.profile_name,
                provider=request.provider or self._provider_name,
                model=request.model or self._default_model,
                role=request.metadata.get("role"),
                latency_ms=1,
                input_tokens=sum(len(message.content.split()) for message in request.messages),
                output_tokens=len(output_text.split()),
                finish_reason="stop",
                metadata={"prompt_kind": request.metadata.get("prompt_kind")},
            ),
        )

    def generate_structured(self, request: StructuredGenerationRequest) -> StructuredGenerationResult:
        response = self.generate(request.request)
        output = self.validate_structured_output(response, request.response_model)
        return StructuredGenerationResult(output=output, response=response)


class NoopEmbeddingClient:
    def __init__(
        self,
        *,
        provider_name: str = "noop",
        default_model: str = "noop-embedding-model",
        dimensions: int = 8,
    ) -> None:
        self._provider_name = provider_name
        self._default_model = default_model
        self._dimensions = dimensions

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        vector = self._vector_for_text(request.input_text, self._dimensions)
        return EmbeddingResponse(
            invocation_id=request.invocation_id,
            provider=request.provider or self._provider_name,
            model=request.model or self._default_model,
            vector=vector,
            trace=ModelInvocationTrace(
                invocation_id=request.invocation_id,
                profile_name=request.profile_name,
                provider=request.provider or self._provider_name,
                model=request.model or self._default_model,
                role="embedding",
                latency_ms=1,
                input_tokens=len(request.input_text.split()),
                output_tokens=None,
                finish_reason="stop",
                metadata={"text_chars": len(request.input_text)},
            ),
        )

    @staticmethod
    def _vector_for_text(text: str, dimensions: int) -> list[float]:
        values = [0.0 for _ in range(dimensions)]
        for token in text.casefold().split():
            digest = sha256(token.encode("utf-8")).digest()
            for index in range(dimensions):
                values[index] += digest[index] / 255.0
        if not any(values):
            return values
        length = sum(value * value for value in values) ** 0.5
        return [value / length for value in values]


__all__ = ["NoopEmbeddingClient", "NoopModelClient"]
