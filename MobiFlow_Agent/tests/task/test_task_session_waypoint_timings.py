from mobiflow_agent.task.session import TaskSession


def test_waypoint_timings_defaults_to_empty_dict():
    session = TaskSession(session_id="s1", goal="test")
    assert session.waypoint_timings == {}


def test_waypoint_timings_accepts_by_step_entries():
    session = TaskSession(session_id="s1", goal="test")
    session.waypoint_timings.setdefault("step-a", {})["entered_at_ms"] = 1000
    session.waypoint_timings["step-a"]["arrived_at_ms"] = 2000
    assert session.waypoint_timings["step-a"] == {"entered_at_ms": 1000, "arrived_at_ms": 2000}
