import pytest

from mobiflow_agent.common.contracts import (
    EntityKind,
    VerificationCheck,
    VerificationPredicate,
    VerificationPredicateOperator,
)
from mobiflow_agent.intake.assembler import SessionAssembly, TestCaseAssembler
from mobiflow_agent.intake.models import TestCase


def _case() -> TestCase:
    return TestCase(
        case_id="case-home",
        raw_goal="Reach home.",
        normalized_goal="Login and reach the home screen.",
        expected_outcomes=[],
    )


def _check() -> VerificationCheck:
    return VerificationCheck(
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


def test_assembler_produces_testcase_shaped_spec() -> None:
    assembly = TestCaseAssembler().assemble(_case(), [_check()])

    assert isinstance(assembly, SessionAssembly)
    assert assembly.goal == "Login and reach the home screen."
    assert assembly.target_kind == EntityKind.TASK
    assert assembly.target_id == "case-home"
    assert assembly.verification_spec.verification_id == "verification:task:case-home:testcase"
    assert assembly.verification_spec.success_checks == [_check()]


def test_assembler_rejects_empty_success_checks() -> None:
    with pytest.raises(ValueError):
        TestCaseAssembler().assemble(_case(), [])
