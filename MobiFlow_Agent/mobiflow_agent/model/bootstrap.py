from __future__ import annotations

from mobiflow_agent.model.base import EmbeddingClient, ModelClient
from mobiflow_agent.model.config import EmbeddingProfile, ModelProfile
from mobiflow_agent.model.providers import (
    OpenAICompatibleEmbeddingClient,
    OpenAICompatibleModelClient,
    OpenAICompatibleProviderConfig,
    UrlLibOpenAICompatibleTransport,
)
from mobiflow_agent.model.runtime import ModelRegistry


class ModelRegistryBuilder:
    def __init__(
        self,
        *,
        profiles: list[ModelProfile] | None = None,
        clients: dict[str, ModelClient] | None = None,
        embedding_profiles: list[EmbeddingProfile] | None = None,
        embedding_clients: dict[str, EmbeddingClient] | None = None,
    ):
        self._profiles = list(profiles or [])
        self._clients = dict(clients or {})
        self._embedding_profiles = list(embedding_profiles or [])
        self._embedding_clients = dict(embedding_clients or {})
        self._provider_configs: dict[str, object] = {}

    def register_profile(self, profile: ModelProfile) -> None:
        self._profiles.append(profile)

    def register_client(self, provider: str, client: ModelClient) -> None:
        self._clients[provider] = client

    def register_embedding_profile(self, profile: EmbeddingProfile) -> None:
        self._embedding_profiles.append(profile)

    def register_embedding_client(self, provider: str, client: EmbeddingClient) -> None:
        self._embedding_clients[provider] = client

    def register_openai_compatible(
        self,
        config: OpenAICompatibleProviderConfig,
        *,
        provider: str = "openai-compatible",
    ) -> None:
        self._provider_configs[provider] = config

    def build(self) -> ModelRegistry:
        clients = dict(self._clients)
        embedding_clients = dict(self._embedding_clients)
        for provider, config in self._provider_configs.items():
            if isinstance(config, OpenAICompatibleProviderConfig):
                transport = UrlLibOpenAICompatibleTransport(
                    base_url=config.base_url,
                    api_key=config.api_key,
                    timeout_seconds=config.timeout_seconds,
                    default_headers=config.default_headers,
                )
                if provider not in clients:
                    clients[provider] = OpenAICompatibleModelClient(transport)
                if provider not in embedding_clients:
                    embedding_clients[provider] = OpenAICompatibleEmbeddingClient(transport)
                continue
            raise ValueError(f"Unsupported provider config for provider: {provider}")
        missing = sorted({profile.provider for profile in self._profiles if profile.provider not in clients})
        if missing:
            raise ValueError(
                "No model client or provider config registered for providers: "
                + ", ".join(missing)
            )
        missing_embedding = sorted(
            {
                profile.provider
                for profile in self._embedding_profiles
                if profile.provider not in embedding_clients
            }
        )
        if missing_embedding:
            raise ValueError(
                "No embedding client or provider config registered for providers: "
                + ", ".join(missing_embedding)
            )
        return ModelRegistry(
            profiles=self._profiles,
            clients=clients,
            embedding_profiles=self._embedding_profiles,
            embedding_clients=embedding_clients,
        )


__all__ = ["ModelRegistryBuilder"]
