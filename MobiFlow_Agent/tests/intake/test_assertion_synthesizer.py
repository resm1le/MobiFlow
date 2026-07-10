from mobiflow_agent.agents.contracts import AgentRole
from mobiflow_agent.common.contracts import VerificationPredicate, VerificationPredicateOperator
from mobiflow_agent.intake.models import AssertionPredicate, ExpectedOutcome, TestCase
from mobiflow_agent.intake.synthesizer import AssertionSynthesizer, SynthesizedAssertion
from mobiflow_agent.model import ModelProfile, ModelRegistry, ModelRuntime, RoleModelPolicy
from mobiflow_agent.model.providers import NoopModelClient


def _runtime(*responses) -> ModelRuntime:
    return ModelRuntime(
        ModelRegistry(
            profiles=[ModelProfile(name="intake-profile", provider="noop", model="noop-model")],
            clients={"noop": NoopModelClient(responses=list(responses))},
        ),
        role_policy=RoleModelPolicy(role_profiles={AgentRole.TASK_INTERPRETER.value: "intake-profile"}),
    )


def _case_with_one_outcome() -> TestCase:
    return TestCase(
        case_id="case-home",
        raw_goal="Reach home.",
        normalized_goal="Reach home.",
        expected_outcomes=[
            ExpectedOutcome(
                raw_text="Home screen is visible",
                predicate=AssertionPredicate.EQUALS,
                observation_fact_id="simulated_screen_snapshot",
                field_path="value.title",
                expected_value="Home Screen",
                confidence=0.9,
            )
        ],
    )


def test_synthesizer_builds_verification_check_from_valid_model_output() -> None:
    good = SynthesizedAssertion(
        check_id="home-screen-visible",
        description="Home Screen is visible.",
        evidence_hint="Home Screen",
        predicates=[
            VerificationPredicate(
                fact_id="simulated_screen_snapshot",
                field_path="value.title",
                operator=VerificationPredicateOperator.EQUALS,
                expected="Home Screen",
            )
        ],
    )
    synthesizer = AssertionSynthesizer(model_runtime=_runtime(good))

    result = synthesizer.synthesize(_case_with_one_outcome())

    assert result.accepted is True
    assert len(result.checks) == 1
    assert result.checks[0].check_id == "home-screen-visible"
    assert result.checks[0].predicates[0].fact_id == "simulated_screen_snapshot"


def test_synthesizer_rejects_unknown_fact_id_then_retries_and_succeeds() -> None:
    bad = SynthesizedAssertion(
        check_id="home-screen-visible",
        description="Home Screen is visible.",
        predicates=[
            VerificationPredicate(
                fact_id="totally_made_up_fact",
                field_path="value.title",
                operator=VerificationPredicateOperator.EQUALS,
                expected="Home Screen",
            )
        ],
    )
    good = SynthesizedAssertion(
        check_id="home-screen-visible",
        description="Home Screen is visible.",
        predicates=[
            VerificationPredicate(
                fact_id="simulated_screen_snapshot",
                field_path="value.title",
                operator=VerificationPredicateOperator.EQUALS,
                expected="Home Screen",
            )
        ],
    )
    synthesizer = AssertionSynthesizer(model_runtime=_runtime(bad, good))

    result = synthesizer.synthesize(_case_with_one_outcome())

    assert result.accepted is True
    assert result.checks[0].predicates[0].fact_id == "simulated_screen_snapshot"


def test_synthesizer_clarifies_when_no_valid_predicate_after_retry() -> None:
    empty = SynthesizedAssertion(
        check_id="home-screen-visible",
        description="Home Screen is visible.",
        evidence_hint="Home Screen",
        predicates=[],
    )
    synthesizer = AssertionSynthesizer(model_runtime=_runtime(empty, empty))

    result = synthesizer.synthesize(_case_with_one_outcome())

    assert result.accepted is False
    assert result.checks == []
    assert result.clarification_questions
