import io
from urllib import error

import pytest

from mobiflow_agent.common.contracts import StrictModel
from mobiflow_agent.model import ModelProfile
from mobiflow_agent.model.base import (
    ModelError,
    ModelMessage,
    ModelRequest,
    StructuredGenerationRequest,
)
from mobiflow_agent.model.bootstrap import ModelRegistryBuilder
from mobiflow_agent.model.providers import (
    OpenAICompatibleModelClient,
    OpenAICompatibleProviderConfig,
    UrlLibOpenAICompatibleTransport,
)


class StructuredValue(StrictModel):
    value: str


class FakeTransport:
    def __init__(self, response):
        self._response = response
        self.payloads = []

    def request_json(self, payload):
        self.payloads.append(payload)
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


def _request() -> ModelRequest:
    return ModelRequest(
        invocation_id="invocation-1",
        profile_name="planner-profile",
        provider="openai-compatible",
        model="gpt-test",
        messages=[ModelMessage(role="user", content="hello")],
        metadata={"role": "planner", "prompt_kind": "planner"},
        temperature=0.2,
        max_output_tokens=128,
    )


def test_openai_compatible_provider_config_reads_env(monkeypatch) -> None:
    monkeypatch.setenv("MOBIFLOW_MODEL_OPENAI_COMPATIBLE_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("MOBIFLOW_MODEL_OPENAI_COMPATIBLE_API_KEY", "secret")
    monkeypatch.setenv("MOBIFLOW_MODEL_OPENAI_COMPATIBLE_TIMEOUT_SECONDS", "12.5")

    config = OpenAICompatibleProviderConfig.from_env()

    assert config.base_url == "https://example.test/v1"
    assert config.api_key == "secret"
    assert config.timeout_seconds == 12.5


def test_model_registry_builder_builds_openai_compatible_client() -> None:
    builder = ModelRegistryBuilder(
        profiles=[ModelProfile(name="planner-profile", provider="openai-compatible", model="gpt-test")]
    )
    builder.register_openai_compatible(
        OpenAICompatibleProviderConfig(
            base_url="https://example.test/v1",
            api_key="secret",
            default_headers={"X-Test": "true"},
        )
    )

    registry = builder.build()

    client = registry.get_client("openai-compatible")
    assert isinstance(client, OpenAICompatibleModelClient)


def test_model_registry_builder_raises_for_missing_provider_config() -> None:
    builder = ModelRegistryBuilder(
        profiles=[ModelProfile(name="planner-profile", provider="openai-compatible", model="gpt-test")]
    )

    with pytest.raises(ValueError, match="openai-compatible"):
        builder.build()


def test_openai_compatible_client_records_usage_and_normalizes_json_string() -> None:
    client = OpenAICompatibleModelClient(
        FakeTransport(
            {
                "choices": [
                    {
                        "message": {"content": '{"value":"ok"}'},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 11, "completion_tokens": 5},
            }
        )
    )

    response = client.generate(_request())

    assert response.output_text == '{"value":"ok"}'
    assert response.structured_output == {"value": "ok"}
    assert response.trace.input_tokens == 11
    assert response.trace.output_tokens == 5
    assert response.trace.finish_reason == "stop"
    assert response.trace.latency_ms >= 1


def test_openai_compatible_client_normalizes_array_content() -> None:
    client = OpenAICompatibleModelClient(
        FakeTransport(
            {
                "choices": [
                    {
                        "message": {
                            "content": [
                                {"type": "output_text", "text": "partial "},
                                {"type": "output_text", "text": "result"},
                            ]
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 4, "completion_tokens": 2},
            }
        )
    )

    response = client.generate(_request())

    assert response.output_text == "partial result"
    assert response.structured_output == [
        {"type": "output_text", "text": "partial "},
        {"type": "output_text", "text": "result"},
    ]


def test_openai_compatible_client_generate_structured_raises_for_invalid_json_string() -> None:
    client = OpenAICompatibleModelClient(
        FakeTransport(
            {
                "choices": [
                    {
                        "message": {"content": "not-json"},
                        "finish_reason": "stop",
                    }
                ]
            }
        )
    )

    with pytest.raises(ModelError, match="valid JSON"):
        client.generate_structured(StructuredGenerationRequest(request=_request(), response_model=StructuredValue))


def test_transport_maps_http_and_invalid_json_errors(monkeypatch) -> None:
    transport = UrlLibOpenAICompatibleTransport(base_url="https://example.test/v1")

    class FakeResponse:
        def __init__(self, payload: bytes):
            self._payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return self._payload

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout: FakeResponse(b"not-json"),
    )
    with pytest.raises(ModelError, match="invalid JSON") as invalid_json:
        transport.request_json({"model": "gpt-test"})
    assert invalid_json.value.code == "INVALID_RESPONSE_JSON"

    http_error = error.HTTPError(
        url="https://example.test/v1/chat/completions",
        code=503,
        msg="boom",
        hdrs=None,
        fp=io.BytesIO(b'{"error":"temporary"}'),
    )
    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout: (_ for _ in ()).throw(http_error))
    with pytest.raises(ModelError) as http_exc:
        transport.request_json({"model": "gpt-test"})
    assert http_exc.value.code == "HTTP_503"
    assert http_exc.value.retryable is True
