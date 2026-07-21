from __future__ import annotations

import json
from pathlib import Path

from mobiflow_agent.waypoint import SequenceCatalog
from mobiflow_agent.waypoint.models import WaypointSequence


PLATFORM_SEQUENCE_FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "AI_Mobile_Executor_Platform"
    / "services"
    / "executor-control-service"
    / "src"
    / "test"
    / "resources"
    / "contracts"
    / "p2-2-resolved-sequence.json"
)


def test_platform_resolved_sequence_fixture_matches_agent_contract() -> None:
    task_payload = json.loads(PLATFORM_SEQUENCE_FIXTURE.read_text(encoding="utf-8"))

    assert isinstance(task_payload.get("goal"), str) and task_payload["goal"].strip()
    sequence = WaypointSequence.model_validate(task_payload["waypoint_sequence"])

    assert sequence.sequence_id == "wechat.text_chat.v1"
    assert sequence.profile_package
    assert sequence.waypoints


def test_platform_fixture_matches_agent_catalog_identity_and_waypoints() -> None:
    task_payload = json.loads(PLATFORM_SEQUENCE_FIXTURE.read_text(encoding="utf-8"))
    platform_sequence = WaypointSequence.model_validate(task_payload["waypoint_sequence"])
    agent_sequence = SequenceCatalog.default().resolve_sequence(platform_sequence.sequence_id)

    assert agent_sequence.sequence_id == platform_sequence.sequence_id
    assert agent_sequence.behavior_label == platform_sequence.behavior_label
    assert agent_sequence.profile_package == platform_sequence.profile_package
    assert [waypoint.waypoint_id for waypoint in agent_sequence.waypoints] == [
        waypoint.waypoint_id for waypoint in platform_sequence.waypoints
    ]
