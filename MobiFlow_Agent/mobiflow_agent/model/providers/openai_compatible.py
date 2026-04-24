from __future__ import annotations

import json
import os
from time import perf_counter
from typing import Any, Protocol
from urllib import error, request

from pydantic import Field

from mobiflow_agent.common.contracts import StrictModel
from mobiflow_agent.model.base import (
    EmbeddingRequest,
    EmbeddingResponse,
    ModelError,
    ModelRequest,
    ModelResponse,
    StructuredGenerationRequest,
    StructuredGenerationResult,
    StructuredModelSupport,
)
from mobiflow_agent.model.telemetry import ModelInvocationTrace


class OpenAICompatibleTransport(Protocol):
    def request_json(self, payload: dict[str, Any], *, endpoint: str = "/chat/completions") -> dict[str, Any]:
        """Submit a JSON payload and return the decoded response."""


class OpenAICompatibleProviderConfig(StrictModel):
    base_url: str = Field(min_length=1)
    api_key: str | None = None
    timeout_seconds: float = Field(default=30.0, gt=0.0)
    default_headers: dict[str, str] = Field(default_factory=dict)

    @classmethod
    def from_env(cls, prefix: str = "MOBIFLOW_MODEL_OPENAI_COMPATIBLE") -> "OpenAICompatibleProviderConfig":
        base_url_key = f"{prefix}_BASE_URL"
        timeout_key = f"{prefix}_TIMEOUT_SECONDS"
        api_key_key = f"{prefix}_API_KEY"
        base_url = os.environ.get(base_url_key, "").strip()
        if not base_url:
            raise ValueError(f"Missing required environment variable: {base_url_key}")
        timeout_raw = os.environ.get(timeout_key, "").strip()
        timeout_seconds = 30.0
        if timeout_raw:
            try:
                timeout_seconds = float(timeout_raw)
            except ValueError as exc:
                raise ValueError(f"Invalid timeout value in environment variable: {timeout_key}") from exc
        api_key = os.environ.get(api_key_key, "").strip() or None
        return cls(
            base_url=base_url,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
        )


class UrlLibOpenAICompatibleTransport:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        timeout_seconds: float = 30.0,
        default_headers: dict[str, str] | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._default_headers = dict(default_headers or {})

    def request_json(self, payload: dict[str, Any], *, endpoint: str = "/chat/completions") -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            **self._default_headers,
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        req = request.Request(f"{self._base_url}{endpoint}", data=body, headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=self._timeout_seconds) as response:
                try:
                    return json.loads(response.read().decode("utf-8"))
                except json.JSONDecodeError as exc:
                    raise ModelError("INVALID_RESPONSE_JSON", "Model provider returned invalid JSON.", retryable=False) from exc
        except error.HTTPError as exc:
            payload_text = exc.read().decode("utf-8", errors="replace")
            raise ModelError(
                f"HTTP_{exc.code}",
                payload_text or f"http_{exc.code}",
                retryable=exc.code >= 500,
            ) from exc
        except OSError as exc:
            raise ModelError("TRANSPORT_ERROR", str(exc), retryable=True) from exc


class OpenAICompatibleModelClient(StructuredModelSupport):
    def __init__(self, transport: OpenAICompatibleTransport):
        self._transport = transport

    @staticmethod
    def _normalize_content(content: Any) -> tuple[str, Any | None]:
        if isinstance(content, dict):
            return json.dumps(content, ensure_ascii=False), content
        if isinstance(content, list):
            text_fragments = [
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and isinstance(part.get("text"), str)
            ]
            output_text = "".join(fragment for fragment in text_fragments if fragment) or json.dumps(
                content,
                ensure_ascii=False,
            )
            return output_text, content
        if isinstance(content, str):
            try:
                decoded = json.loads(content)
            except json.JSONDecodeError:
                return content, None
            return content, decoded
        if content is None:
            return "", None
        return json.dumps(content, ensure_ascii=False, default=str), content

    @staticmethod
    def _build_payload(request: ModelRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [message.model_dump(mode="python") for message in request.messages],
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_output_tokens is not None:
            payload["max_tokens"] = request.max_output_tokens
        return payload

    def generate(self, request):
        started_at = perf_counter()
        response = self._transport.request_json(self._build_payload(request))
        latency_ms = max(1, int((perf_counter() - started_at) * 1000))
        choice = (response.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        content = message.get("content") or ""
        output_text, structured_output = self._normalize_content(content)
        usage = response.get("usage") or {}
        return ModelResponse(
            invocation_id=request.invocation_id,
            provider=request.provider,
            model=request.model,
            output_text=output_text,
            structured_output=structured_output,
            trace=ModelInvocationTrace(
                invocation_id=request.invocation_id,
                profile_name=request.profile_name,
                provider=request.provider,
                model=request.model,
                role=request.metadata.get("role"),
                latency_ms=latency_ms,
                input_tokens=usage.get("prompt_tokens"),
                output_tokens=usage.get("completion_tokens"),
                finish_reason=choice.get("finish_reason"),
                metadata={"prompt_kind": request.metadata.get("prompt_kind")},
            ),
        )

    def generate_structured(self, request: StructuredGenerationRequest) -> StructuredGenerationResult:
        response = self.generate(request.request)
        output = self.validate_structured_output(response, request.response_model)
        return StructuredGenerationResult(output=output, response=response)


class OpenAICompatibleEmbeddingClient:
    def __init__(self, transport: OpenAICompatibleTransport):
        self._transport = transport

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        started_at = perf_counter()
        response = self._transport.request_json(
            {
                "model": request.model,
                "input": request.input_text,
            },
            endpoint="/embeddings",
        )
        latency_ms = max(1, int((perf_counter() - started_at) * 1000))
        data = (response.get("data") or [{}])[0]
        vector = data.get("embedding")
        if not isinstance(vector, list) or not all(isinstance(value, (int, float)) for value in vector):
            raise ModelError(
                "INVALID_EMBEDDING_RESPONSE",
                "Embedding provider did not return a numeric embedding vector.",
                retryable=False,
            )
        usage = response.get("usage") or {}
        return EmbeddingResponse(
            invocation_id=request.invocation_id,
            provider=request.provider,
            model=request.model,
            vector=[float(value) for value in vector],
            trace=ModelInvocationTrace(
                invocation_id=request.invocation_id,
                profile_name=request.profile_name,
                provider=request.provider,
                model=request.model,
                role="embedding",
                latency_ms=latency_ms,
                input_tokens=usage.get("prompt_tokens"),
                output_tokens=None,
                finish_reason="stop",
                metadata={"text_chars": len(request.input_text)},
            ),
        )


__all__ = [
    "OpenAICompatibleEmbeddingClient",
    "OpenAICompatibleModelClient",
    "OpenAICompatibleProviderConfig",
    "OpenAICompatibleTransport",
    "UrlLibOpenAICompatibleTransport",
]
