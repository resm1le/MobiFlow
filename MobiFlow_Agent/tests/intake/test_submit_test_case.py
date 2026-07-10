from mobiflow_agent.agents.contracts import AgentRole
from mobiflow_agent.common.contracts import VerificationPredicate, VerificationPredicateOperator
from mobiflow_agent.intake.interpreter import TestCaseParser
from mobiflow_agent.intake.models import AssertionPredicate, ExpectedOutcome, TaskIntakeStatus, TestCase
from mobiflow_agent.intake.service import TaskIntakeService
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


def _home_case() -> TestCase:
    return TestCase(
        case_id="case-home",
        raw_goal="Login and reach home.",
        normalized_goal="Login and reach the home screen.",
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
        needs_confirmation=False,
    )


def _home_assertion() -> SynthesizedAssertion:
    return SynthesizedAssertion(
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


def test_create_session_from_text_still_uses_template_path() -> None:
    result = TaskIntakeService().create_session_from_text(
        "Login to the demo app and reach home screen."
    )

    assert result.status == TaskIntakeStatus.READY
    assert result.session is not None
    assert result.session.target_id == "dynamic_login_success"


def test_submit_test_case_creates_session_with_testcase_spec() -> None:
    parser = TestCaseParser(model_runtime=_runtime(_home_case()))
    synthesizer = AssertionSynthesizer(model_runtime=_runtime(_home_assertion()))
    service = TaskIntakeService(parser=parser, synthesizer=synthesizer)

    result = service.submit_test_case("Login and confirm the home screen is visible.")

    assert result.status == TaskIntakeStatus.READY
    assert result.test_case is not None
    assert result.session is not None
    spec = result.session.initial_verification_spec
    assert spec is not None
    assert spec.verification_id == "verification:task:case-home:testcase"
    assert spec.success_checks[0].check_id == "home-screen-visible"


def test_submit_test_case_clarifies_when_parser_fails() -> None:
    parser = TestCaseParser(model_runtime=_runtime(ValueError("boom")))
    synthesizer = AssertionSynthesizer(model_runtime=_runtime())
    service = TaskIntakeService(parser=parser, synthesizer=synthesizer)

    result = service.submit_test_case("gibberish")

    assert result.status == TaskIntakeStatus.NEEDS_CLARIFICATION
    assert result.session is None
    assert result.clarification_questions
