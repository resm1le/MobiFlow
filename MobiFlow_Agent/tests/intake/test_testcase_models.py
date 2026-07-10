from mobiflow_agent.common.contracts import ApprovalMode, VerificationPredicateOperator
from mobiflow_agent.intake.models import (
    AssertionPredicate,
    ExpectedOutcome,
    OutcomeOrigin,
    TestCase,
    TestStep,
)


def test_assertion_predicate_aliases_crown_operator_vocabulary() -> None:
    assert {member.value for member in AssertionPredicate} == {
        member.value for member in VerificationPredicateOperator
    }


def test_testcase_builds_with_expected_outcome_and_defaults() -> None:
    case = TestCase(
        case_id="case-logout",
        raw_goal="Log out and confirm the login button disappears.",
        normalized_goal="Log out and confirm the login button disappears.",
        steps=[TestStep(raw_text="Tap the logout button", hint_action="mobile.tap")],
        expected_outcomes=[
            ExpectedOutcome(
                raw_text="Login button is gone",
                predicate=AssertionPredicate.NOT_EXISTS,
                observation_fact_id="simulated_ui_tree",
                field_path="value[].node_id",
                confidence=0.9,
            )
        ],
    )

    assert case.approval_mode == ApprovalMode.ON_RISK
    assert case.needs_confirmation is True
    assert case.expected_outcomes[0].origin == OutcomeOrigin.MODEL_SYNTHESIZED
    assert case.expected_outcomes[0].expected_value is None
