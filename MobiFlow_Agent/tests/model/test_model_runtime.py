from mobiflow_agent.common.contracts import StrictModel
from mobiflow_agent.model import ModelError, ModelProfile, ModelRegistry, ModelSettings, ModelRuntime, RoleModelPolicy
from mobiflow_agent.model.prompting import PromptBundle
from mobiflow_agent.model.providers import NoopModelClient
from mobiflow_agent.agents import AgentRole
from mobiflow_agent.runtime.context import StepContextSummary


class SampleStructuredOutput(StrictModel):
    value: str


def test_noop_model_runtime_returns_structured_output() -> None:
    runtime = ModelRuntime(
        ModelRegistry(
            profiles=[ModelProfile(name="planner-profile", provider="noop", model="noop-model")],
            clients={"noop": NoopModelClient(responses=[{"value": "ok"}])},
        ),
        role_policy=RoleModelPolicy(role_profiles={AgentRole.PLANNER.value: "planner-profile"}),
    )

    result = runtime.generate_structured(
        role=AgentRole.PLANNER,
        prompt=PromptBundle(system_prompt="system", user_prompt="user"),
        response_model=SampleStructuredOutput,
    )

    assert result.output.value == "ok"
    assert result.response.trace.provider == "noop"
    assert result.response.trace.model == "noop-model"
    assert result.response.trace.finish_reason == "stop"


def test_model_runtime_emits_error_trace_and_uses_fallback_profile() -> None:
    traces = []
    runtime = ModelRuntime(
        ModelRegistry(
            profiles=[
                ModelProfile(
                    name="primary",
                    provider="noop",
                    model="noop-primary",
                    settings=ModelSettings(fallback_profile="fallback"),
                ),
                ModelProfile(name="fallback", provider="noop", model="noop-fallback"),
            ],
            clients={
                "noop": NoopModelClient(
                    responses=[
                        ModelError("TIMEOUT", "primary timed out", retryable=True),
                        {"value": "fallback-ok"},
                    ]
                )
            },
        ),
        role_policy=RoleModelPolicy(role_profiles={AgentRole.PLANNER.value: "primary"}),
        telemetry_sink=traces.append,
    )

    result = runtime.generate_structured(
        role=AgentRole.PLANNER,
        prompt=PromptBundle(system_prompt="system", user_prompt="user"),
        response_model=SampleStructuredOutput,
    )

    assert result.output.value == "fallback-ok"
    assert len(traces) == 2
    assert traces[0].profile_name == "primary"
    assert traces[0].error_code == "TIMEOUT"
    assert traces[1].profile_name == "fallback"
    assert traces[1].fallback_from_profile == "primary"


def test_model_runtime_raises_for_schema_validation_failure() -> None:
    runtime = ModelRuntime(
        ModelRegistry(
            profiles=[ModelProfile(name="planner-profile", provider="noop", model="noop-model")],
            clients={"noop": NoopModelClient(responses=[{"unexpected": "field"}])},
        ),
        role_policy=RoleModelPolicy(role_profiles={AgentRole.PLANNER.value: "planner-profile"}),
    )

    try:
        runtime.generate_structured(
            role=AgentRole.PLANNER,
            prompt=PromptBundle(system_prompt="system", user_prompt="user"),
            response_model=SampleStructuredOutput,
        )
    except ModelError as exc:
        assert exc.code == "SCHEMA_VALIDATION_FAILED"
    else:
        raise AssertionError("Expected schema validation to fail.")


def test_model_runtime_compacts_context_payload_and_records_trace_metadata() -> None:
    runtime = ModelRuntime(
        ModelRegistry(
            profiles=[
                ModelProfile(
                    name="planner-profile",
                    provider="noop",
                    model="noop-model",
                    settings=ModelSettings(input_token_budget=50, compaction_target_tokens=40),
                )
            ],
            clients={"noop": NoopModelClient(responses=[{"value": "ok"}])},
        ),
        role_policy=RoleModelPolicy(role_profiles={AgentRole.PLANNER.value: "planner-profile"}),
    )

    result = runtime.generate_structured(
        role=AgentRole.PLANNER,
        prompt=PromptBundle(
            system_prompt="system",
            context_payload={
                "goal": "Inspect blocked task",
                "proposal": {"tool": "cancel_run"},
                "memory_context": {"history": "x" * 1000, "items": list(range(50))},
                "session_digest": {
                    "summary": "y" * 1000,
                    "recent_step_summaries": [{"summary": "z" * 1000}],
                },
            },
            preserve_keys=["goal", "proposal"],
        ),
        response_model=SampleStructuredOutput,
    )

    assert result.output.value == "ok"
    assert result.response.trace.metadata["context_compacted"] is True
    assert (
        result.response.trace.metadata["estimated_input_tokens_after"]
        <= result.response.trace.metadata["estimated_input_tokens_before"]
    )


def test_model_runtime_exposes_profile_lookup_and_history_summary() -> None:
    runtime = ModelRuntime(
        ModelRegistry(
            profiles=[ModelProfile(name="summary-profile", provider="noop", model="noop-model")],
            clients={"noop": NoopModelClient(responses=['summary text'])},
        ),
    )

    profile = runtime.get_profile("summary-profile")
    summary = runtime.summarize_history(
        [
            StepContextSummary(
                step_id="step-1",
                step_kind="observe",
                goal="Observe task",
                outcome_status="completed",
                summary="Observed the task state.",
            )
        ],
        profile_name="summary-profile",
    )

    assert profile.provider == "noop"
    assert summary == "summary text"


def test_model_runtime_history_summary_failure_returns_none() -> None:
    runtime = ModelRuntime(
        ModelRegistry(
            profiles=[ModelProfile(name="summary-profile", provider="noop", model="noop-model")],
            clients={"noop": NoopModelClient(responses=[ModelError("TIMEOUT", "timed out", retryable=True)])},
        ),
    )

    summary = runtime.summarize_history(
        [
            StepContextSummary(
                step_id="step-1",
                step_kind="verify",
                goal="Verify task",
                outcome_status="failed",
                summary="Verification could not finish.",
            )
        ],
        profile_name="summary-profile",
    )

    assert summary is None
