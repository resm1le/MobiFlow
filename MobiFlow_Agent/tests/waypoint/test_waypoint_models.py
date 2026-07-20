import pytest
from pydantic import ValidationError

from mobiflow_agent.common.contracts import (
    EntityKind,
    VerificationCheck,
    VerificationSpec,
)
from mobiflow_agent.waypoint.models import (
    PathConstraint,
    RendezvousSpec,
    Waypoint,
    WaypointSequence,
    WaypointStrength,
)


def _arrival_spec(waypoint_id: str) -> VerificationSpec:
    return VerificationSpec(
        verification_id=f"verification:{waypoint_id}",
        target_kind=EntityKind.TASK,
        target_id=waypoint_id,
        success_checks=[
            VerificationCheck(
                check_id=f"{waypoint_id}-check",
                description="Arrived at waypoint.",
                evidence_hint="Home Screen",
            )
        ],
    )


def _waypoint(waypoint_id: str) -> Waypoint:
    return Waypoint(
        waypoint_id=waypoint_id,
        description=f"Reach {waypoint_id}.",
        arrival_spec=_arrival_spec(waypoint_id),
    )


def test_waypoint_defaults_to_commonsense_and_no_constraint():
    wp = _waypoint("logged_in")
    assert wp.strength == WaypointStrength.COMMONSENSE
    assert wp.path_constraint is None
    assert wp.rendezvous is None


def test_strict_waypoint_carries_path_constraint():
    wp = Waypoint(
        waypoint_id="call_connected",
        description="Reach connected call.",
        arrival_spec=_arrival_spec("call_connected"),
        strength=WaypointStrength.STRICT,
        path_constraint=PathConstraint(
            required_screens=["chat", "call_dialog"],
            forbidden_actions=["search"],
        ),
    )
    assert wp.strength == WaypointStrength.STRICT
    assert wp.path_constraint.required_screens == ["chat", "call_dialog"]
    assert wp.path_constraint.forbidden_actions == ["search"]


def test_rendezvous_is_optional_and_stored():
    wp = Waypoint(
        waypoint_id="call_started",
        description="Start a call.",
        arrival_spec=_arrival_spec("call_started"),
        rendezvous=RendezvousSpec(barrier_id="call-1", role="caller"),
    )
    assert wp.rendezvous.role == "caller"


def test_sequence_requires_at_least_one_waypoint():
    with pytest.raises(ValidationError):
        WaypointSequence(
            sequence_id="wechat.text_chat.v1",
            behavior_label="wechat_text_chat",
            profile_package="com.tencent.mm",
            waypoints=[],
        )


def test_sequence_rejects_duplicate_waypoint_ids():
    with pytest.raises(ValidationError):
        WaypointSequence(
            sequence_id="s1",
            behavior_label="b1",
            profile_package="pkg",
            waypoints=[_waypoint("dup"), _waypoint("dup")],
        )


def test_sequence_extra_field_forbidden():
    with pytest.raises(ValidationError):
        WaypointSequence(
            sequence_id="s1",
            behavior_label="b1",
            profile_package="pkg",
            waypoints=[_waypoint("logged_in")],
            unexpected="x",
        )
