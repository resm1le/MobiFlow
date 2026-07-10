from mobiflow_agent.intake.models import AssertionPredicate, ExpectedOutcome, TestCase, TestStep
from mobiflow_agent.intake.validation import TestCaseValidator


def _outcome() -> ExpectedOutcome:
    return ExpectedOutcome(
        raw_text="Home screen is visible",
        predicate=AssertionPredicate.EQUALS,
        observation_fact_id="simulated_screen_snapshot",
        field_path="value.title",
        expected_value="Home Screen",
        confidence=0.9,
    )


def test_validator_accepts_structurally_legal_case() -> None:
    case = TestCase(
        case_id="case-1",
        raw_goal="Login and reach home.",
        normalized_goal="Login and reach home.",
        steps=[TestStep(raw_text="Tap login", hint_action="mobile.tap")],
        expected_outcomes=[_outcome()],
        needs_confirmation=False,
    )

    result = TestCaseValidator().validate(case)

    assert result.accepted is True
    assert result.issues == []


def test_validator_rejects_case_without_expected_outcome() -> None:
    case = TestCase(
        case_id="case-2",
        raw_goal="Do something.",
        normalized_goal="Do something.",
        expected_outcomes=[],
        needs_confirmation=False,
    )

    result = TestCaseValidator().validate(case)

    assert result.accepted is False
    assert "missing_expected_outcome" in result.issues
    assert result.clarification_questions


def test_validator_rejects_disallowed_hint_action() -> None:
    case = TestCase(
        case_id="case-3",
        raw_goal="Login.",
        normalized_goal="Login.",
        steps=[TestStep(raw_text="Run a shell", hint_action="mobile.shell")],
        expected_outcomes=[_outcome()],
        needs_confirmation=False,
    )

    result = TestCaseValidator().validate(case)

    assert result.accepted is False
    assert "disallowed_action:mobile.shell" in result.issues


def test_validator_preserves_risk_confirmation_gate() -> None:
    case = TestCase(
        case_id="case-4",
        raw_goal="Delete account.",
        normalized_goal="Delete the simulated account.",
        expected_outcomes=[_outcome()],
        risk_flags=["destructive_action"],
        needs_confirmation=True,
    )

    blocked = TestCaseValidator().validate(case, confirmed=False)
    confirmed = TestCaseValidator().validate(case, confirmed=True)

    assert blocked.accepted is False
    assert "confirmation_required" in blocked.issues
    assert confirmed.accepted is True
