from mobiflow_agent.common.contracts import EntityKind
from mobiflow_agent.task.plan import TaskStep, TaskStepKind, TaskStepPolicy
from mobiflow_agent.waypoint.models import PathConstraint


def _policy() -> TaskStepPolicy:
    return TaskStepPolicy(policy_id="policy:x", description="Bounded actions.")


def test_task_step_path_constraint_defaults_to_none():
    step = TaskStep(
        step_id="s1",
        kind=TaskStepKind.DYNAMIC,
        goal="Reach x.",
        policy=_policy(),
    )
    assert step.path_constraint is None


def test_task_step_accepts_path_constraint():
    step = TaskStep(
        step_id="s1",
        kind=TaskStepKind.DYNAMIC,
        goal="Reach x.",
        policy=_policy(),
        path_constraint=PathConstraint(
            required_screens=["chat"],
            forbidden_actions=["search"],
        ),
    )
    assert step.path_constraint.required_screens == ["chat"]
    assert step.path_constraint.forbidden_actions == ["search"]
