from mobiflow_agent.common.contracts import (
    EntityKind,
    VerificationCheck,
    VerificationSpec,
)
from mobiflow_agent.runtime.trace_export import ExecutionTraceExporter
from mobiflow_agent.task.plan import TaskPlan, TaskStep, TaskStepKind, TaskStepPolicy
from mobiflow_agent.task.session import TaskSession


def _step(step_id: str) -> TaskStep:
    return TaskStep(
        step_id=step_id,
        kind=TaskStepKind.DYNAMIC,
        goal=f"Reach {step_id}.",
        allowed_side_effects=[],
        verification_spec=VerificationSpec(
            verification_id=f"v:{step_id}",
            target_kind=EntityKind.TASK,
            target_id=step_id,
            success_checks=[
                VerificationCheck(check_id="c", description="d", evidence_hint="e")
            ],
        ),
        policy=TaskStepPolicy(policy_id=f"p:{step_id}", description="."),
    )


def _session_with_timings(behavior_label: str | None) -> TaskSession:
    session = TaskSession(session_id="s1", goal="test")
    session.plan = TaskPlan(
        plan_id="plan-1",
        summary="test plan",
        behavior_label=behavior_label,
        steps=[_step("stepA"), _step("stepB")],
    )
    session.waypoint_timings = {
        "stepA": {"entered_at_ms": 1000, "arrived_at_ms": 1500},
        "stepB": {"entered_at_ms": 1600, "arrived_at_ms": 2500},
    }
    return session


def test_export_json_includes_waypoint_segments_in_plan_order():
    exporter = ExecutionTraceExporter()
    exported = exporter.export_json(_session_with_timings("shopping_checkout"))
    segments = exported["waypoint_segments"]
    assert [seg["step_id"] for seg in segments] == ["stepA", "stepB"]
    assert all(seg["behavior_label"] == "shopping_checkout" for seg in segments)
    assert segments[0]["entered_at_ms"] == 1000
    assert segments[0]["arrived_at_ms"] == 1500
    assert segments[0]["dwell_ms"] == 500
    assert segments[1]["dwell_ms"] == 900


def test_waypoint_segments_omit_step_when_no_timings():
    session = _session_with_timings("b")
    session.waypoint_timings = {
        "stepA": {"entered_at_ms": 1000, "arrived_at_ms": 1500}
    }
    exported = ExecutionTraceExporter().export_json(session)
    segments = exported["waypoint_segments"]
    assert len(segments) == 2
    assert segments[1]["step_id"] == "stepB"
    assert segments[1]["entered_at_ms"] is None
    assert segments[1]["arrived_at_ms"] is None
    assert segments[1]["dwell_ms"] is None


def test_waypoint_segments_behavior_label_none_when_missing():
    exported = ExecutionTraceExporter().export_json(_session_with_timings(None))
    assert exported["waypoint_segments"][0]["behavior_label"] is None


def test_waypoint_segments_empty_when_no_plan():
    session = TaskSession(session_id="s1", goal="test")
    exported = ExecutionTraceExporter().export_json(session)
    assert exported["waypoint_segments"] == []
