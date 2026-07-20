from mobiflow_agent.common.contracts import (
    EntityKind,
    VerificationCheck,
    VerificationSpec,
)
from mobiflow_agent.graph import TaskGraphRuntime
from mobiflow_agent.waypoint import Waypoint, WaypointSequence


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


def test_create_session_from_waypoint_sequence_sets_plan():
    runtime = TaskGraphRuntime()
    session = runtime.create_session(
        "Collect shopping checkout traffic.",
        target_kind=EntityKind.TASK,
        target_id="shopping_checkout",
        waypoint_sequence=_sequence(),
    )
    assert session.plan is not None
    assert session.plan.behavior_label == "shopping_checkout"
    assert [step.step_id for step in session.plan.steps] == ["logged_in", "ordered"]
    # current_step 尚未激活(留给 run→ensure_plan)
    assert session.current_step is None


def test_create_session_without_sequence_leaves_plan_none():
    runtime = TaskGraphRuntime()
    session = runtime.create_session(
        "No sequence provided.",
        target_kind=EntityKind.TASK,
        target_id="x",
    )
    assert session.plan is None
