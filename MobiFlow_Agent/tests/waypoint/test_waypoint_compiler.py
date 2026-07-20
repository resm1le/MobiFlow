from mobiflow_agent.common.contracts import (
    EntityKind,
    VerificationCheck,
    VerificationSpec,
)
from mobiflow_agent.task.plan import TaskPlan, TaskStepKind
from mobiflow_agent.waypoint import (
    Waypoint,
    WaypointSequence,
    compile_sequence_to_plan,
)


def _arrival_spec(waypoint_id: str) -> VerificationSpec:
    return VerificationSpec(
        verification_id=f"verification:{waypoint_id}",
        target_kind=EntityKind.TASK,
        target_id=waypoint_id,
        success_checks=[
            VerificationCheck(
                check_id=f"{waypoint_id}-check",
                description="Arrived.",
                evidence_hint="hint",
            )
        ],
    )


def _sequence() -> WaypointSequence:
    return WaypointSequence(
        sequence_id="shopping.checkout.v1",
        behavior_label="shopping_checkout",
        profile_package="com.example.shop",
        waypoints=[
            Waypoint(
                waypoint_id="logged_in",
                description="Reach logged-in state.",
                arrival_spec=_arrival_spec("logged_in"),
            ),
            Waypoint(
                waypoint_id="ordered",
                description="Reach order-placed state.",
                arrival_spec=_arrival_spec("ordered"),
            ),
        ],
    )


def test_compile_produces_taskplan_with_one_step_per_waypoint():
    plan = compile_sequence_to_plan(_sequence())
    assert isinstance(plan, TaskPlan)
    assert [step.step_id for step in plan.steps] == ["logged_in", "ordered"]


def test_compiled_steps_are_dynamic_with_policy_and_arrival_spec():
    plan = compile_sequence_to_plan(_sequence())
    first = plan.steps[0]
    assert first.kind == TaskStepKind.DYNAMIC
    assert first.policy is not None
    assert first.policy.max_iterations == 3
    assert first.goal == "Reach logged-in state."
    assert first.verification_spec is not None
    assert first.verification_spec.verification_id == "verification:logged_in"


def test_compiled_plan_summary_mentions_behavior_label():
    plan = compile_sequence_to_plan(_sequence())
    assert "shopping_checkout" in plan.summary


def test_compiled_step_policy_id_follows_waypoint_convention():
    plan = compile_sequence_to_plan(_sequence())
    assert plan.steps[0].policy.policy_id == "policy:logged_in"
    assert plan.steps[1].policy.policy_id == "policy:ordered"


def test_compiled_step_does_not_carry_waypoint_only_fields():
    plan = compile_sequence_to_plan(_sequence())
    step = plan.steps[0]
    for field_name in ("strength", "path_constraint", "rendezvous"):
        assert not hasattr(step, field_name)
