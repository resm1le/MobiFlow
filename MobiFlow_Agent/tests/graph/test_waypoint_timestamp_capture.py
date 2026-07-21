from mobiflow_agent.agents.observer import ObserverAgent
from mobiflow_agent.agents.recovery import RecoveryAgent
from mobiflow_agent.agents.step_policy import StepPolicyAgent
from mobiflow_agent.agents.verifier import VerifierAgent
from mobiflow_agent.agents.contracts import StepDecision, StepDecisionType
from mobiflow_agent.common.contracts import (
    EntityKind,
    EvidenceKind,
    EvidenceRef,
    ObservationFact,
    ObservationFactSource,
    ObservationView,
    VerificationCheck,
    VerificationSpec,
)
from mobiflow_agent.graph import TaskGraphRuntime
from mobiflow_agent.runtime.trace_export import ExecutionTraceExporter
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
                evidence_hint=waypoint_id,
            )
        ],
    )


def _observation(observation_id: str, screen_id: str) -> ObservationView:
    return ObservationView(
        observation_id=observation_id,
        focus_kind=EntityKind.TASK,
        focus_id=screen_id,
        facts=[
            ObservationFact(
                fact_id="mobile_observation_summary",
                source=ObservationFactSource.PLATFORM,
                title="Mobile observation summary",
                value={"screen_id": screen_id},
                evidence_refs=[
                    EvidenceRef(
                        evidence_id=f"evidence:{observation_id}",
                        kind=EvidenceKind.PLATFORM_SNAPSHOT,
                        summary=f"Screen {screen_id} observed.",
                        locator=screen_id,
                    )
                ],
            )
        ],
    )


def _sequence() -> WaypointSequence:
    return WaypointSequence(
        sequence_id="capture.v1",
        behavior_label="capture_flow",
        profile_package="com.example.app",
        waypoints=[
            Waypoint(
                waypoint_id="stepA",
                description="Reach stepA.",
                arrival_spec=_arrival_spec("stepA"),
            ),
            Waypoint(
                waypoint_id="stepB",
                description="Reach stepB.",
                arrival_spec=_arrival_spec("stepB"),
            ),
        ],
    )


def test_run_records_entered_and_arrived_timestamps_per_step():
    ticks = {"n": 0}

    def clock() -> int:
        ticks["n"] += 100
        return ticks["n"]

    observations = iter([_observation("obs-a", "stepA"), _observation("obs-b", "stepB")])

    runtime = TaskGraphRuntime(
        observer_agent=ObserverAgent(observation_provider=lambda _s: next(observations)),
        step_policy_agent=StepPolicyAgent(
            step_policy=lambda _s: StepDecision(
                decision_id="d",
                decision_type=StepDecisionType.STEP_SUCCEEDED,
                summary="Reached.",
            )
        ),
        verifier_agent=VerifierAgent(),
        recovery_agent=RecoveryAgent(),
        clock=clock,
    )
    session = runtime.create_session(
        "capture timing test",
        target_kind=EntityKind.TASK,
        target_id="stepA",
        waypoint_sequence=_sequence(),
    )
    completed = runtime.run(session)

    timings = completed.waypoint_timings
    assert set(timings.keys()) == {"stepA", "stepB"}
    for step_id in ("stepA", "stepB"):
        entry = timings[step_id]
        assert "entered_at_ms" in entry
        assert "arrived_at_ms" in entry
        assert entry["arrived_at_ms"] >= entry["entered_at_ms"]
    assert timings["stepA"]["entered_at_ms"] < timings["stepB"]["entered_at_ms"]


def test_clock_defaults_when_not_injected():
    observations = iter([_observation("obs-a", "stepA")])
    runtime = TaskGraphRuntime(
        observer_agent=ObserverAgent(observation_provider=lambda _s: next(observations)),
        step_policy_agent=StepPolicyAgent(
            step_policy=lambda _s: StepDecision(
                decision_id="d",
                decision_type=StepDecisionType.STEP_SUCCEEDED,
                summary="Reached.",
            )
        ),
        verifier_agent=VerifierAgent(),
        recovery_agent=RecoveryAgent(),
    )
    seq = WaypointSequence(
        sequence_id="s1",
        behavior_label="b1",
        profile_package="pkg",
        waypoints=[Waypoint(waypoint_id="stepA", description="A.", arrival_spec=_arrival_spec("stepA"))],
    )
    session = runtime.create_session(
        "default clock test",
        target_kind=EntityKind.TASK,
        target_id="stepA",
        waypoint_sequence=seq,
    )
    completed = runtime.run(session)
    entry = completed.waypoint_timings["stepA"]
    assert isinstance(entry["entered_at_ms"], int)
    assert isinstance(entry["arrived_at_ms"], int)
    assert entry["arrived_at_ms"] >= entry["entered_at_ms"]


def test_reactivating_step_preserves_entry_without_reading_clock_again():
    ticks = iter([100, 200])
    runtime = TaskGraphRuntime(clock=lambda: next(ticks))
    session = runtime.create_session("reactivation", waypoint_sequence=_sequence())

    runtime._activate_step(session, 0)
    runtime._activate_step(session, 0)

    assert session.waypoint_timings["stepA"]["entered_at_ms"] == 100
    assert next(ticks) == 200


def test_skipping_step_records_arrival_before_activating_next_step():
    ticks = iter([100, 200, 300])
    runtime = TaskGraphRuntime(clock=lambda: next(ticks))
    session = runtime.create_session("skip timing", waypoint_sequence=_sequence())

    runtime._activate_step(session, 0)
    runtime._complete_step_without_verification(session)

    assert session.waypoint_timings["stepA"] == {
        "entered_at_ms": 100,
        "arrived_at_ms": 200,
    }
    assert session.waypoint_timings["stepB"] == {"entered_at_ms": 300}


def test_e2e_waypoint_segments_deterministic_under_injected_clock():
    ticks = {"n": 0}

    def clock() -> int:
        ticks["n"] += 100
        return ticks["n"]

    observations = iter([_observation("obs-a", "stepA"), _observation("obs-b", "stepB")])

    runtime = TaskGraphRuntime(
        observer_agent=ObserverAgent(observation_provider=lambda _s: next(observations)),
        step_policy_agent=StepPolicyAgent(
            step_policy=lambda _s: StepDecision(
                decision_id="d",
                decision_type=StepDecisionType.STEP_SUCCEEDED,
                summary="Reached.",
            )
        ),
        verifier_agent=VerifierAgent(),
        recovery_agent=RecoveryAgent(),
        clock=clock,
    )
    session = runtime.create_session(
        "e2e timeline",
        target_kind=EntityKind.TASK,
        target_id="stepA",
        waypoint_sequence=_sequence(),
    )
    completed = runtime.run(session)

    segments = ExecutionTraceExporter().export_json(completed)["waypoint_segments"]

    assert [segment["step_id"] for segment in segments] == ["stepA", "stepB"]
    assert all(segment["behavior_label"] == "capture_flow" for segment in segments)
    for segment in segments:
        assert isinstance(segment["entered_at_ms"], int)
        assert isinstance(segment["arrived_at_ms"], int)
        assert segment["dwell_ms"] == segment["arrived_at_ms"] - segment["entered_at_ms"]
        assert segment["dwell_ms"] >= 0
    assert segments[0]["arrived_at_ms"] <= segments[1]["entered_at_ms"]
