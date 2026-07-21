"""把一条航点序列编译成可被 TaskGraphRuntime 执行的 TaskPlan。"""

from __future__ import annotations

from mobiflow_agent.common.ids import build_task_plan_id
from mobiflow_agent.task.plan import (
    TaskPlan,
    TaskStep,
    TaskStepKind,
    TaskStepPolicy,
)
from mobiflow_agent.waypoint.models import Waypoint, WaypointSequence


def _compile_step(waypoint: Waypoint) -> TaskStep:
    return TaskStep(
        step_id=waypoint.waypoint_id,
        kind=TaskStepKind.DYNAMIC,
        goal=waypoint.description,
        allowed_side_effects=list(waypoint.allowed_actions),
        verification_spec=waypoint.arrival_spec,
        path_constraint=waypoint.path_constraint,
        policy=TaskStepPolicy(
            policy_id=f"policy:{waypoint.waypoint_id}",
            description=f"Bounded actions to reach waypoint {waypoint.waypoint_id}.",
            max_iterations=3,
        ),
    )


def compile_sequence_to_plan(sequence: WaypointSequence) -> TaskPlan:
    return TaskPlan(
        plan_id=build_task_plan_id(),
        summary=(
            f"Waypoint sequence {sequence.sequence_id} "
            f"for behavior {sequence.behavior_label}."
        ),
        behavior_label=sequence.behavior_label,
        steps=[_compile_step(wp) for wp in sequence.waypoints],
    )
