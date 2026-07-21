from __future__ import annotations

import pytest
from pydantic import ValidationError

from mobiflow_agent.agents.contracts import AgentRole
from mobiflow_agent.common.contracts import (
    DEFAULT_MOBILE_ACTIONS,
    PathConstraint,
    VerificationPredicate,
    VerificationPredicateOperator,
)
from mobiflow_agent.intake.models import (
    AssertionPredicate,
    ExpectedOutcome,
    TaskIntakeStatus,
    TestCase,
)
from mobiflow_agent.model import ModelProfile, ModelRegistry, ModelRuntime, RoleModelPolicy
from mobiflow_agent.model.providers import NoopModelClient
from mobiflow_agent.intake.synthesizer import SynthesizedAssertion
from mobiflow_agent.waypoint import SequenceCatalog
from mobiflow_agent.waypoint.drafting import (
    DraftWaypointCandidate,
    SequenceDraftRequest,
    SequenceDraftResult,
    SequenceDraftService,
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


def _synthesized_assertion(check_id: str, title: str) -> SynthesizedAssertion:
    return SynthesizedAssertion(
        check_id=check_id,
        description=f"{title} is visible.",
        predicates=[
            VerificationPredicate(
                fact_id="simulated_screen_snapshot",
                field_path="value.title",
                operator=VerificationPredicateOperator.EQUALS,
                expected=title,
            )
        ],
    )


def _two_waypoint_candidate() -> SequenceWaypointDraftCandidate:
    return SequenceWaypointDraftCandidate(
        waypoints=[
            DraftWaypointCandidate(
                waypoint_id="logged_in",
                description="Reach the logged-in screen.",
                arrival_outcomes=[_outcome("The logged-in home screen is visible")],
                path_constraint=PathConstraint(
                    required_screens=["launch"],
                    forbidden_actions=["logout"],
                ),
            ),
            DraftWaypointCandidate(
                waypoint_id="chat_open",
                description="Reach the target chat.",
                arrival_outcomes=[_outcome("The target chat is visible")],
                allowed_actions=["mobile.tap", "mobile.wait"],
            ),
        ]
    )


def test_draft_service_builds_atomic_multi_waypoint_sequence() -> None:
    runtime = _runtime(
        _test_case(),
        _two_waypoint_candidate(),
        _synthesized_assertion("logged-in-visible", "Home"),
        _synthesized_assertion("chat-visible", "Chat"),
    )
    service = SequenceDraftService(model_runtime=runtime)

    result = service.draft_sequence(_request())

    assert result.status == TaskIntakeStatus.READY
    assert result.sequence is not None
    assert result.sequence.sequence_id == "wechat.home.v1"
    assert result.sequence.behavior_label == "wechat_home"
    assert result.sequence.profile_package == "com.tencent.mm"
    assert [waypoint.waypoint_id for waypoint in result.sequence.waypoints] == [
        "logged_in",
        "chat_open",
    ]
    assert [
        waypoint.arrival_spec.target_id for waypoint in result.sequence.waypoints
    ] == ["logged_in", "chat_open"]
    assert result.sequence.waypoints[0].arrival_spec.success_checks[0].check_id == (
        "logged-in-visible"
    )
    assert result.sequence.waypoints[1].arrival_spec.success_checks[0].check_id == (
        "chat-visible"
    )
    assert result.sequence.waypoints[0].path_constraint is not None
    assert result.sequence.waypoints[1].allowed_actions == ["mobile.tap", "mobile.wait"]
    assert len(result.trace_refs) == 4
    assert len(result.trace_refs) == len(set(result.trace_refs))


def test_draft_service_without_runtime_requests_clarification() -> None:
    result = SequenceDraftService(model_runtime=None).draft_sequence(_request())

    assert result.status == TaskIntakeStatus.NEEDS_CLARIFICATION
    assert result.sequence is None
    assert result.clarification_questions


def test_draft_service_returns_clarification_when_decomposition_fails() -> None:
    runtime = _runtime(_test_case(), ValueError("boom"))

    result = SequenceDraftService(model_runtime=runtime).draft_sequence(_request())

    assert result.status == TaskIntakeStatus.NEEDS_CLARIFICATION
    assert result.sequence is None
    assert "waypoint_decomposition_model_error" in result.issues
    assert len(result.trace_refs) == 1


def test_draft_service_returns_clarification_when_assertion_is_not_observable() -> None:
    empty = SynthesizedAssertion(
        check_id="not-observable",
        description="No observable predicate.",
        predicates=[],
    )
    runtime = _runtime(_test_case(), _candidate(), empty, empty)

    result = SequenceDraftService(model_runtime=runtime).draft_sequence(_request())

    assert result.status == TaskIntakeStatus.NEEDS_CLARIFICATION
    assert result.sequence is None
    assert "waypoint:logged_in:no_predicate" in result.issues
    assert len(result.trace_refs) == 4


def test_draft_service_rejects_duplicate_waypoint_ids() -> None:
    duplicate = SequenceWaypointDraftCandidate(
        waypoints=[
            DraftWaypointCandidate(
                waypoint_id="duplicate",
                description="First duplicate.",
                arrival_outcomes=[_outcome()],
            ),
            DraftWaypointCandidate(
                waypoint_id="duplicate",
                description="Second duplicate.",
                arrival_outcomes=[_outcome()],
            ),
        ]
    )
    runtime = _runtime(_test_case(), duplicate)

    result = SequenceDraftService(model_runtime=runtime).draft_sequence(_request())

    assert result.status == TaskIntakeStatus.REJECTED
    assert result.sequence is None
    assert result.issues == ["duplicate_waypoint_id:duplicate"]


def test_draft_service_rejects_disallowed_waypoint_action() -> None:
    candidate = SequenceWaypointDraftCandidate(
        waypoints=[
            DraftWaypointCandidate(
                waypoint_id="unsafe",
                description="Reach unsafe state.",
                arrival_outcomes=[_outcome()],
                allowed_actions=["mobile.tap", "shell.exec"],
            )
        ]
    )
    runtime = _runtime(_test_case(), candidate)

    result = SequenceDraftService(model_runtime=runtime).draft_sequence(_request())

    assert result.status == TaskIntakeStatus.REJECTED
    assert result.sequence is None
    assert result.issues == ["waypoint:unsafe:disallowed_action:shell.exec"]


def test_draft_service_preserves_execution_risks_as_warnings_only() -> None:
    parsed = _test_case().model_copy(
        update={"risk_flags": ["account_mutation"], "needs_confirmation": True}
    )
    runtime = _runtime(
        parsed,
        _candidate(),
        _synthesized_assertion("home-visible", "Home"),
    )

    result = SequenceDraftService(model_runtime=runtime).draft_sequence(_request())

    assert result.status == TaskIntakeStatus.READY
    assert result.warnings == ["execution_risk:account_mutation"]


def test_draft_service_does_not_mutate_sequence_catalog() -> None:
    catalog = SequenceCatalog.default()
    before = catalog.list_sequences()
    runtime = _runtime(
        _test_case(),
        _candidate(),
        _synthesized_assertion("home-visible", "Home"),
    )

    result = SequenceDraftService(model_runtime=runtime).draft_sequence(_request())

    assert result.status == TaskIntakeStatus.READY
    assert catalog.list_sequences() == before
