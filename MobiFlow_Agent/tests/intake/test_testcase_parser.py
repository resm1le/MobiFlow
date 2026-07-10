from mobiflow_agent.agents.contracts import AgentRole
from mobiflow_agent.intake.interpreter import TestCaseParser
from mobiflow_agent.intake.models import AssertionPredicate, TaskIntakeStatus, TestCase
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


def test_parser_returns_ready_testcase_from_model_output() -> None:
    draft = TestCase(
        case_id="case-logout",
        raw_goal="Log out and confirm the login button disappears.",
        normalized_goal="Log out and confirm the login button disappears.",
        expected_outcomes=[],
    )
    parser = TestCaseParser(model_runtime=_runtime(draft))

    result = parser.parse("Log out and confirm the login button disappears.")

    assert result.status == TaskIntakeStatus.READY
    assert result.test_case is not None
    assert result.test_case.case_id == "case-logout"
    assert result.trace_refs


def test_parser_returns_clarification_on_model_failure() -> None:
    parser = TestCaseParser(model_runtime=_runtime(ValueError("boom")))

    result = parser.parse("something unparseable")

    assert result.status == TaskIntakeStatus.NEEDS_CLARIFICATION
    assert result.test_case is None
    assert result.clarification_questions


def test_parser_without_runtime_asks_for_clarification_not_template_gate() -> None:
    parser = TestCaseParser(model_runtime=None)

    result = parser.parse("totally novel goal with no template match")

    assert result.status == TaskIntakeStatus.NEEDS_CLARIFICATION
    assert result.test_case is None
    assert "scenario_id" not in result.issues
