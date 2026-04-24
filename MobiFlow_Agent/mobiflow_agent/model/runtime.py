from __future__ import annotations

from typing import Any, Callable, TypeVar
from uuid import uuid4

from mobiflow_agent.agents.contracts import AgentRole
from mobiflow_agent.model.base import (
    EmbeddingClient,
    ModelClient,
    ModelError,
    ModelMessage,
    ModelRequest,
    StructuredGenerationRequest,
    StructuredGenerationResult,
)
from mobiflow_agent.model.config import EmbeddingProfile, ModelProfile, RoleModelPolicy
from mobiflow_agent.model.prompting import PromptBundle
from mobiflow_agent.model.telemetry import ModelInvocationTrace
from mobiflow_agent.runtime.context import ContextCompressionService

T = TypeVar("T")
TelemetrySink = Callable[[ModelInvocationTrace], None]


class ModelRegistry:
    def __init__(
        self,
        *,
        profiles: list[ModelProfile] | None = None,
        clients: dict[str, ModelClient] | None = None,
        embedding_profiles: list[EmbeddingProfile] | None = None,
        embedding_clients: dict[str, EmbeddingClient] | None = None,
    ):
        self._profiles = {profile.name: profile for profile in profiles or []}
        self._clients = dict(clients or {})
        self._embedding_profiles = {
            profile.name: profile for profile in embedding_profiles or []
        }
        self._embedding_clients = dict(embedding_clients or {})

    def register_profile(self, profile: ModelProfile) -> None:
        self._profiles[profile.name] = profile

    def register_client(self, provider: str, client: ModelClient) -> None:
        self._clients[provider] = client

    def register_embedding_profile(self, profile: EmbeddingProfile) -> None:
        self._embedding_profiles[profile.name] = profile

    def register_embedding_client(self, provider: str, client: EmbeddingClient) -> None:
        self._embedding_clients[provider] = client

    def get_profile(self, profile_name: str) -> ModelProfile:
        try:
            return self._profiles[profile_name]
        except KeyError as exc:
            raise ValueError(f"Unknown model profile: {profile_name}") from exc

    def get_client(self, provider: str) -> ModelClient:
        try:
            return self._clients[provider]
        except KeyError as exc:
            raise ValueError(f"No model client registered for provider: {provider}") from exc

    def get_embedding_profile(self, profile_name: str) -> EmbeddingProfile:
        try:
            return self._embedding_profiles[profile_name]
        except KeyError as exc:
            raise ValueError(f"Unknown embedding profile: {profile_name}") from exc

    def get_embedding_client(self, provider: str) -> EmbeddingClient:
        try:
            return self._embedding_clients[provider]
        except KeyError as exc:
            raise ValueError(f"No embedding client registered for provider: {provider}") from exc


class ModelRuntime:
    def __init__(
        self,
        registry: ModelRegistry,
        *,
        role_policy: RoleModelPolicy | None = None,
        telemetry_sink: TelemetrySink | None = None,
        context_compressor: ContextCompressionService | None = None,
    ):
        self._registry = registry
        self._role_policy = role_policy or RoleModelPolicy()
        self._telemetry_sink = telemetry_sink
        self._context_compressor = context_compressor or ContextCompressionService()

    def resolve_profile_name(self, role: AgentRole | str, override: str | None = None) -> str | None:
        return override or self._role_policy.resolve(role)

    def get_profile(self, profile_name: str) -> ModelProfile:
        return self._registry.get_profile(profile_name)

    def get_embedding_profile(self, profile_name: str) -> EmbeddingProfile:
        return self._registry.get_embedding_profile(profile_name)

    def embed_text(self, text: str, *, profile_name: str, metadata: dict[str, Any] | None = None) -> list[float]:
        profile = self.get_embedding_profile(profile_name)
        client = self._registry.get_embedding_client(profile.provider)
        request = self._build_embedding_request(
            profile=profile,
            text=text,
            metadata=metadata,
        )
        previous_profile_name: str | None = None
        attempt_index = 0
        current_profile = profile
        while True:
            try:
                response = client.embed(request)
                trace = response.trace.model_copy(
                    update={
                        "retry_count": attempt_index,
                        "fallback_from_profile": previous_profile_name,
                    }
                )
                self._emit_trace(trace)
                return response.vector
            except ModelError as exc:
                trace = ModelInvocationTrace(
                    invocation_id=request.invocation_id,
                    profile_name=current_profile.name,
                    provider=current_profile.provider,
                    model=current_profile.model,
                    role="embedding",
                    latency_ms=0,
                    error_code=exc.code,
                    retry_count=attempt_index,
                    fallback_from_profile=previous_profile_name,
                    metadata={"text_chars": len(text)},
                )
                self._emit_trace(trace)
                if exc.retryable and attempt_index < current_profile.max_retries:
                    attempt_index += 1
                    continue
                raise

    def generate_structured(
        self,
        *,
        role: AgentRole,
        prompt: PromptBundle,
        response_model: type[T],
        profile_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> StructuredGenerationResult[T]:
        resolved_profile_name = self.resolve_profile_name(role, override=profile_name)
        if resolved_profile_name is None:
            raise ValueError(f"No model profile configured for role: {role.value}")
        previous_profile_name: str | None = None
        current_profile_name = resolved_profile_name
        attempt_index = 0
        while True:
            profile = self.get_profile(current_profile_name)
            prompt_result = self._prepare_prompt(
                role=role,
                profile=profile,
                prompt=prompt,
            )
            request = ModelRequest(
                invocation_id=f"model-invocation:{uuid4().hex}",
                profile_name=profile.name,
                provider=profile.provider,
                model=profile.model,
                messages=[
                    ModelMessage(role="system", content=prompt.system_prompt),
                    ModelMessage(role="user", content=prompt_result.user_prompt),
                ],
                metadata={
                    "role": role.value,
                    "prompt_kind": prompt.metadata.get("prompt_kind"),
                    "context_compacted": prompt_result.compacted,
                    "estimated_input_tokens_before": prompt_result.estimated_input_tokens_before,
                    "estimated_input_tokens_after": prompt_result.estimated_input_tokens_after,
                    "used_summary_profile": prompt_result.used_summary_profile,
                    "used_imported_handoff": prompt_result.used_imported_handoff,
                    **(metadata or {}),
                },
                timeout_ms=profile.settings.timeout_ms,
                max_retries=profile.settings.max_retries,
                temperature=profile.settings.temperature,
                max_output_tokens=profile.settings.max_output_tokens,
            )
            client = self._registry.get_client(profile.provider)
            try:
                result = client.generate_structured(
                    StructuredGenerationRequest(
                        request=request,
                        response_model=response_model,
                    )
                )
                trace = result.response.trace.model_copy(
                    update={
                        "retry_count": attempt_index,
                        "fallback_from_profile": previous_profile_name,
                        "metadata": {
                            **result.response.trace.metadata,
                            "context_compacted": prompt_result.compacted,
                            "estimated_input_tokens_before": prompt_result.estimated_input_tokens_before,
                            "estimated_input_tokens_after": prompt_result.estimated_input_tokens_after,
                            "used_summary_profile": prompt_result.used_summary_profile,
                            "used_imported_handoff": prompt_result.used_imported_handoff,
                        },
                    }
                )
                result.response = result.response.model_copy(update={"trace": trace})
                self._emit_trace(trace)
                return result
            except ModelError as exc:
                trace = ModelInvocationTrace(
                    invocation_id=request.invocation_id,
                    profile_name=profile.name,
                    provider=profile.provider,
                    model=profile.model,
                    role=role.value,
                    latency_ms=0,
                    error_code=exc.code,
                    retry_count=attempt_index,
                    fallback_from_profile=previous_profile_name,
                    metadata={
                        "prompt_kind": prompt.metadata.get("prompt_kind"),
                        "context_compacted": prompt_result.compacted,
                        "estimated_input_tokens_before": prompt_result.estimated_input_tokens_before,
                        "estimated_input_tokens_after": prompt_result.estimated_input_tokens_after,
                        "used_summary_profile": prompt_result.used_summary_profile,
                        "used_imported_handoff": prompt_result.used_imported_handoff,
                    },
                )
                self._emit_trace(trace)
                if exc.retryable and attempt_index < profile.settings.max_retries:
                    attempt_index += 1
                    continue
                if profile.settings.fallback_profile is not None and profile.settings.fallback_profile != current_profile_name:
                    previous_profile_name = current_profile_name
                    current_profile_name = profile.settings.fallback_profile
                    attempt_index = 0
                    continue
                raise

    def _emit_trace(self, trace: ModelInvocationTrace) -> None:
        if self._telemetry_sink is not None:
            self._telemetry_sink(trace)

    def _prepare_prompt(
        self,
        *,
        role: AgentRole,
        profile: ModelProfile,
        prompt: PromptBundle,
    ):
        if not prompt.context_payload:
            return self._context_compressor.compact_prompt(
                system_prompt=prompt.system_prompt,
                payload={"prompt": prompt.user_prompt},
                preserve_keys=["prompt"],
                input_token_budget=profile.settings.input_token_budget,
                compaction_target_tokens=profile.settings.compaction_target_tokens,
                summary_profile=profile.settings.summary_profile,
            ).model_copy(update={"user_prompt": prompt.user_prompt})

        history_summarizer = None
        if profile.settings.summary_profile is not None:
            history_summarizer = lambda steps: self.summarize_history(
                steps,
                profile_name=profile.settings.summary_profile,
            )
        return self._context_compressor.compact_prompt(
            system_prompt=prompt.system_prompt,
            payload=prompt.context_payload,
            preserve_keys=prompt.preserve_keys,
            input_token_budget=profile.settings.input_token_budget,
            compaction_target_tokens=profile.settings.compaction_target_tokens,
            summary_profile=profile.settings.summary_profile,
            history_summarizer=history_summarizer,
        )

    def summarize_history(self, steps, *, profile_name: str) -> str | None:
        if not steps:
            return None
        profile = self.get_profile(profile_name)
        client = self._registry.get_client(profile.provider)
        request = ModelRequest(
            invocation_id=f"model-summary:{uuid4().hex}",
            profile_name=profile.name,
            provider=profile.provider,
            model=profile.model,
            messages=[
                ModelMessage(
                    role="system",
                    content="Summarize historical agent context into one compact paragraph. Preserve risks and outcomes.",
                ),
                ModelMessage(
                    role="user",
                    content=str([step.model_dump(mode='python') for step in steps]),
                ),
            ],
            metadata={"role": "context_compressor", "prompt_kind": "context_summary"},
            timeout_ms=profile.settings.timeout_ms,
            max_retries=profile.settings.max_retries,
            temperature=profile.settings.temperature,
            max_output_tokens=profile.settings.max_output_tokens,
        )
        try:
            response = client.generate(request)
        except ModelError:
            return None
        self._emit_trace(response.trace)
        return response.output_text.strip() or None

    @staticmethod
    def _build_embedding_request(
        *,
        profile: EmbeddingProfile,
        text: str,
        metadata: dict[str, Any] | None,
    ):
        from mobiflow_agent.model.base import EmbeddingRequest

        return EmbeddingRequest(
            invocation_id=f"embedding-invocation:{uuid4().hex}",
            profile_name=profile.name,
            provider=profile.provider,
            model=profile.model,
            input_text=text,
            metadata=metadata or {},
            timeout_ms=profile.timeout_ms,
            max_retries=profile.max_retries,
        )


__all__ = ["ModelRegistry", "ModelRuntime"]
