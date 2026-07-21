from __future__ import annotations

import pytest
from pydantic import ValidationError

from mobiflow_agent.agents.contracts import AgentRole
from mobiflow_agent.common.contracts import DEFAULT_MOBILE_ACTIONS
from mobiflow_agent.intake.models import (
    AssertionPredicate,
    ExpectedOutcome,
    TaskIntakeStatus,
    TestCase,
)
from mobiflow_agent.model import ModelProfile, ModelRegistry, ModelRuntime, RoleModelPolicy
from mobiflow_agent.model.providers import NoopModelClient
from mobiflow_agent.waypoint import SequenceCatalog
from mobiflow_agent.waypoint.drafting import (
    DraftWaypointCandidate,
    SequenceDraftRequest,
    SequenceDraftResult,
    SequenceDraftSourceKind,
    SequenceWaypointDraftCandidate,
    WaypointDraftDecomposer,
)
from mobiflow_agent.waypoint.prompting import WaypointDraftPromptBuilder


def _outcome(text: str = "Home is visible") -> ExpectedOutcome:
    return ExpectedOutcome(
        raw_text=text,
        predicate=AssertionPredicate.EXISTS,
        observation_fact_id="simulated_screen_snapshot",
        field_path="value.title",
        confidence=0.9,
    )


def _candidate() -> SequenceWaypointDraftCandidate:
    return SequenceWaypointDraftCandidate(
        waypoints=[
            DraftWaypointCandidate(
                waypoint_id="logged_in",
                description="Reach the logged-in home screen.",
                arrival_outcomes=[_outcome()],
            )
        ]
    )


def _request(**updates) -> SequenceDraftRequest:
    values = {
        "source_text": "Open WeChat and reach the home screen.",
        "source_kind": SequenceDraftSourceKind.NATURAL_LANGUAGE,
        "sequence_id": "wechat.home.v1",
        "behavior_label": "wechat_home",
        "profile_package": "com.tencent.mm",
    }
    values.update(updates)
    return SequenceDraftRequest(**values)


def _test_case() -> TestCase:
    return TestCase(
        case_id="case-home",
        raw_goal="Open WeChat and reach the home screen.",
        normalized_goal="Reach the WeChat home screen.",
        expected_outcomes=[_outcome()],
    )


def _runtime(*responses, telemetry_sink=None) -> ModelRuntime:
    return ModelRuntime(
        ModelRegistry(
            profiles=[ModelProfile(name="intake-profile", provider="noop", model="noop-model")],
            clients={"noop": NoopModelClient(responses=list(responses))},
        ),
        role_policy=RoleModelPolicy(
            role_profiles={AgentRole.TASK_INTERPRETER.value: "intake-profile"}
        ),
        telemetry_sink=telemetry_sink,
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_text", ""),
        ("sequence_id", "wechat.home"),
        ("sequence_id", "Wechat.Home.v1"),
        ("behavior_label", ""),
        ("profile_package", ""),
    ],
)
def test_draft_request_rejects_invalid_identity_and_source(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        _request(**{field: value})


def test_draft_candidate_requires_waypoints_and_arrival_outcomes() -> None:
    with pytest.raises(ValidationError):
        SequenceWaypointDraftCandidate(waypoints=[])
    with pytest.raises(ValidationError):
        DraftWaypointCandidate(
            waypoint_id="logged_in",
            description="Reach home.",
            arrival_outcomes=[],
        )


def test_draft_result_enforces_status_sequence_invariant() -> None:
    sequence = SequenceCatalog.default().resolve_sequence("wechat.text_chat.v1")

    with pytest.raises(ValidationError):
        SequenceDraftResult(status=TaskIntakeStatus.READY)
    with pytest.raises(ValidationError):
        SequenceDraftResult(
            status=TaskIntakeStatus.NEEDS_CLARIFICATION,
            sequence=sequence,
        )

    assert SequenceDraftResult(
        status=TaskIntakeStatus.READY,
        sequence=sequence,
    ).sequence == sequence


def test_draft_candidate_mutable_defaults_are_isolated() -> None:
    first = DraftWaypointCandidate(
        waypoint_id="first",
        description="Reach first.",
        arrival_outcomes=[_outcome()],
    )
    second = DraftWaypointCandidate(
        waypoint_id="second",
        description="Reach second.",
        arrival_outcomes=[_outcome()],
    )

    first.allowed_actions.append("mobile.first_only")

    assert second.allowed_actions == list(DEFAULT_MOBILE_ACTIONS)
    assert "mobile.first_only" not in DEFAULT_MOBILE_ACTIONS


def test_waypoint_draft_prompt_contains_authoritative_context_and_constraints() -> None:
    prompt = WaypointDraftPromptBuilder().build(
        test_case=_test_case(),
        request=_request(source_kind=SequenceDraftSourceKind.LEGACY_SCRIPT),
        allowed_actions=list(DEFAULT_MOBILE_ACTIONS),
    )

    assert prompt.context_payload["source_kind"] == "legacy_script"
    assert prompt.context_payload["sequence_metadata"] == {
        "sequence_id": "wechat.home.v1",
        "behavior_label": "wechat_home",
        "profile_package": "com.tencent.mm",
    }
    assert prompt.context_payload["test_case"]["case_id"] == "case-home"
    assert prompt.context_payload["allowed_actions"] == list(DEFAULT_MOBILE_ACTIONS)
    assert "device" in prompt.system_prompt.casefold()
    assert "rendezvous" in prompt.system_prompt.casefold()
    assert "catalog" in prompt.system_prompt.casefold()


def test_decomposer_returns_candidate_and_model_trace() -> None:
    decomposer = WaypointDraftDecomposer(model_runtime=_runtime(_candidate()))

    result = decomposer.decompose(_test_case(), request=_request())

    assert result.accepted is True
    assert result.candidate == _candidate()
    assert len(result.trace_refs) == 1


def test_decomposer_uses_task_interpreter_role_and_profile_override() -> None:
    traces = []
    runtime = _runtime(_candidate(), telemetry_sink=traces.append)
    decomposer = WaypointDraftDecomposer(model_runtime=runtime)

    result = decomposer.decompose(
        _test_case(),
        request=_request(),
        profile_name="intake-profile",
    )

    assert result.accepted is True
    assert result.trace_refs
    assert traces[0].role == AgentRole.TASK_INTERPRETER.value
    assert traces[0].profile_name == "intake-profile"


def test_decomposer_without_runtime_requests_clarification() -> None:
    result = WaypointDraftDecomposer(model_runtime=None).decompose(
        _test_case(),
        request=_request(),
    )

    assert result.accepted is False
    assert result.candidate is None
    assert result.clarification_questions


def test_decomposer_converts_model_failure_to_controlled_result() -> None:
    result = WaypointDraftDecomposer(
        model_runtime=_runtime(ValueError("boom"))
    ).decompose(_test_case(), request=_request())

    assert result.accepted is False
    assert result.candidate is None
    assert result.issues == ["waypoint_decomposition_model_error"]
    assert result.clarification_questions
