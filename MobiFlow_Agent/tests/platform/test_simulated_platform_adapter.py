from __future__ import annotations

from mobiflow_agent.common.contracts import EntityKind, ExecutionProposal
from mobiflow_agent.evaluation.scenario.fixtures import login_success_case
from mobiflow_agent.platform.simulation import (
    MOBILE_OBSERVATION_SUMMARY_FACT_ID,
    SIMULATED_SCREEN_FACT_ID,
    SIMULATED_UI_TREE_FACT_ID,
    SimulatedMobilePlatformAdapter,
)
from mobiflow_agent.platform.types import GovernedActionState
from mobiflow_agent.runtime.state import CallerContext


def _caller_context() -> CallerContext:
    return CallerContext(
        session_id="session-1",
        agent_task_id="task-1",
        turn_id="turn-1",
        step_id="step-1",
    )


def _proposal(action: str, arguments: dict) -> ExecutionProposal:
    return ExecutionProposal(
        proposal_id=f"proposal:{action}:{len(arguments)}",
        action_tool_name=action,
        arguments=arguments,
        target_kind=EntityKind.TASK,
        target_id="login_success",
        rationale=f"Run {action}.",
    )


def test_observe_target_returns_screen_evidence() -> None:
    adapter = SimulatedMobilePlatformAdapter(login_success_case().platform_scenario)

    observation = adapter.observe_target(EntityKind.TASK, "login_success")
    facts = {fact.fact_id: fact for fact in observation.facts}

    assert observation.focus_kind == EntityKind.TASK
    assert SIMULATED_SCREEN_FACT_ID in facts
    assert MOBILE_OBSERVATION_SUMMARY_FACT_ID in facts
    assert SIMULATED_UI_TREE_FACT_ID in facts
    assert facts[SIMULATED_SCREEN_FACT_ID].value["screen_id"] == "launcher"
    assert facts[MOBILE_OBSERVATION_SUMMARY_FACT_ID].value["screen_id"] == "launcher"
    assert isinstance(facts[MOBILE_OBSERVATION_SUMMARY_FACT_ID].value["visible_node_ids"], list)
    assert facts[SIMULATED_SCREEN_FACT_ID].evidence_refs[0].handle is not None


def test_simulated_actions_advance_screen_and_record_trace() -> None:
    adapter = SimulatedMobilePlatformAdapter(login_success_case().platform_scenario)

    launch = adapter.submit_execution_proposal(
        _proposal("mobile.launch", {"app": "demo"}),
        _caller_context(),
    )
    username = adapter.submit_execution_proposal(
        _proposal("mobile.input_text", {"node_id": "username", "text": "alice"}),
        _caller_context(),
    )

    assert launch.state == GovernedActionState.EXECUTED
    assert username.state == GovernedActionState.EXECUTED
    assert adapter.current_screen_id == "username_entered"
    assert [trace.action_tool_name for trace in adapter.action_traces] == [
        "mobile.launch",
        "mobile.input_text",
    ]
    assert adapter.action_traces[-1].from_screen_id == "login_blank"
    assert adapter.action_traces[-1].to_screen_id == "username_entered"


def test_missing_transition_returns_failed_result_without_changing_screen() -> None:
    adapter = SimulatedMobilePlatformAdapter(login_success_case().platform_scenario)

    result = adapter.submit_execution_proposal(
        _proposal("mobile.tap", {"node_id": "missing"}),
        _caller_context(),
    )

    assert result.state == GovernedActionState.FAILED
    assert result.error is not None
    assert result.error.code == "SIMULATED_TRANSITION_NOT_FOUND"
    assert adapter.current_screen_id == "launcher"


def test_approval_transition_waits_for_resolution_before_screen_change() -> None:
    from mobiflow_agent.evaluation.scenario.fixtures import approval_required_destructive_action_case

    case = approval_required_destructive_action_case()
    adapter = SimulatedMobilePlatformAdapter(case.platform_scenario, target_id=case.scenario_id)
    proposal = case.requests[0].proposal
    assert proposal is not None

    pending = adapter.submit_execution_proposal(proposal, _caller_context())

    assert pending.state == GovernedActionState.APPROVAL_REQUIRED
    assert pending.confirmation_id is not None
    assert adapter.current_screen_id == "settings"

    completed = adapter.resolve_approval(pending.confirmation_id, True, _caller_context())

    assert completed.state == GovernedActionState.EXECUTED
    assert adapter.current_screen_id == "deleted"
    assert adapter.action_traces[-1].approved is True
