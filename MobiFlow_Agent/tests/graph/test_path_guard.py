from mobiflow_agent.common.contracts import (
    EntityKind,
    ExecutionProposal,
    ObservationFact,
    ObservationFactSource,
    ObservationView,
)
from mobiflow_agent.task.plan import TaskStep, TaskStepKind, TaskStepPolicy
from mobiflow_agent.waypoint.models import PathConstraint
from mobiflow_agent.graph.path_guard import (
    OFF_STANDARD_PATH,
    evaluate_path_constraint,
)


def _step(path_constraint: PathConstraint | None) -> TaskStep:
    return TaskStep(
        step_id="s1",
        kind=TaskStepKind.DYNAMIC,
        goal="Reach x.",
        allowed_side_effects=["tap_element"],
        path_constraint=path_constraint,
        policy=TaskStepPolicy(policy_id="policy:x", description="Bounded."),
    )


def _proposal(action: str) -> ExecutionProposal:
    return ExecutionProposal(
        proposal_id="p1",
        action_tool_name=action,
        arguments={"element": "ok"},
        rationale="advance",
    )


def _observation(screen_id: str | None) -> ObservationView:
    value = {"screen_id": screen_id} if screen_id is not None else {}
    return ObservationView(
        observation_id="obs-1",
        focus_kind=EntityKind.TASK,
        focus_id="s1",
        facts=[
            ObservationFact(
                fact_id="mobile_observation_summary",
                source=ObservationFactSource.PLATFORM,
                title="Mobile observation summary",
                value=value,
            )
        ],
    )


def test_no_constraint_returns_none():
    result = evaluate_path_constraint(_step(None), _observation("chat"), _proposal("tap_element"))
    assert result is None


def test_forbidden_action_is_flagged():
    constraint = PathConstraint(forbidden_actions=["search"])
    result = evaluate_path_constraint(_step(constraint), _observation("chat"), _proposal("search"))
    assert result is not None


def test_allowed_action_on_required_screen_passes():
    constraint = PathConstraint(required_screens=["chat"], forbidden_actions=["search"])
    result = evaluate_path_constraint(_step(constraint), _observation("chat"), _proposal("tap_element"))
    assert result is None


def test_wrong_screen_is_flagged():
    constraint = PathConstraint(required_screens=["chat"])
    result = evaluate_path_constraint(_step(constraint), _observation("moments"), _proposal("tap_element"))
    assert result is not None


def test_missing_screen_id_is_flagged_when_required_screens_set():
    constraint = PathConstraint(required_screens=["chat"])
    result = evaluate_path_constraint(_step(constraint), _observation(None), _proposal("tap_element"))
    assert result is not None


def test_none_observation_is_flagged_when_required_screens_set():
    constraint = PathConstraint(required_screens=["chat"])
    result = evaluate_path_constraint(_step(constraint), None, _proposal("tap_element"))
    assert result is not None


def test_empty_constraint_lists_pass():
    constraint = PathConstraint()  # 两个列表都空
    result = evaluate_path_constraint(_step(constraint), _observation("anything"), _proposal("tap_element"))
    assert result is None
