from mobiflow_agent.agents.contracts import AgentRole, StepDecision, StepDecisionType
from mobiflow_agent.agents.executor import ExecutorAgent
from mobiflow_agent.agents.observer import ObserverAgent
from mobiflow_agent.agents.recovery import RecoveryAgent
from mobiflow_agent.agents.step_policy import StepPolicyAgent
from mobiflow_agent.agents.verifier import VerifierAgent
from mobiflow_agent.common.contracts import (
    EntityKind,
    EvidenceKind,
    EvidenceRef,
    ExecutionProposal,
    ObservationFact,
    ObservationFactSource,
    ObservationView,
    VerificationCheck,
    VerificationSpec,
)
from mobiflow_agent.graph import TaskGraphRuntime
from mobiflow_agent.platform.adapter import FakePlatformAdapter
from mobiflow_agent.platform.types import GovernedActionResult, GovernedActionState
from mobiflow_agent.waypoint import Waypoint, WaypointSequence


def _arrival_spec() -> VerificationSpec:
    return VerificationSpec(
        verification_id="verification:tap-complete",
        target_kind=EntityKind.TASK,
        target_id="tap_complete",
        success_checks=[
            VerificationCheck(
                check_id="tap-complete",
                description="The tap action reached the waypoint.",
                evidence_hint="arrived",
            )
        ],
    )


def _sequence(*, allowed_actions: list[str] | None = None) -> WaypointSequence:
    waypoint_kwargs = {}
    if allowed_actions is not None:
        waypoint_kwargs["allowed_actions"] = allowed_actions
    return WaypointSequence(
        sequence_id="tap.sequence.v1",
        behavior_label="tap_sequence",
        profile_package="com.example.app",
        waypoints=[
            Waypoint(
                waypoint_id="tap_complete",
                description="Tap the target and reach the completed state.",
                arrival_spec=_arrival_spec(),
                **waypoint_kwargs,
            )
        ],
    )


def _observation(observation_id: str, status: str) -> ObservationView:
    return ObservationView(
        observation_id=observation_id,
        focus_kind=EntityKind.TASK,
        focus_id="tap_complete",
        facts=[
            ObservationFact(
                fact_id=f"fact:{observation_id}",
                source=ObservationFactSource.PLATFORM,
                title="Waypoint observation",
                value={"status": status},
                evidence_refs=[
                    EvidenceRef(
                        evidence_id=f"evidence:{observation_id}",
                        kind=EvidenceKind.PLATFORM_SNAPSHOT,
                        summary=f"Waypoint status is {status}.",
                        locator="tap_complete",
                    )
                ],
            )
        ],
    )


def _tap_proposal() -> ExecutionProposal:
    return ExecutionProposal(
        proposal_id="proposal:tap-target",
        action_tool_name="mobile.tap",
        arguments={"node_id": "target"},
        target_kind=EntityKind.TASK,
        target_id="tap_complete",
        rationale="Tap the target to reach the waypoint.",
    )


def test_waypoint_default_actions_allow_mobile_action_execution() -> None:
    adapter = FakePlatformAdapter(
        submit_results=[
            GovernedActionResult(
                state=GovernedActionState.EXECUTED,
                proposal_id="proposal:tap-target",
                action_tool_name="mobile.tap",
                result={"ok": True},
            )
        ]
    )
    observations = [
        _observation("observation:ready", "ready"),
        _observation("observation:arrived", "arrived"),
    ]

    def decide(session):
        if session.last_execution_result is None:
            return StepDecision(
                decision_id="decision:tap",
                decision_type=StepDecisionType.PROPOSE_EXECUTION,
                summary="Tap the target.",
                proposal=_tap_proposal(),
            )
        return StepDecision(
            decision_id="decision:succeeded",
            decision_type=StepDecisionType.STEP_SUCCEEDED,
            summary="The tap waypoint has been reached.",
        )

    runtime = TaskGraphRuntime(
        observer_agent=ObserverAgent(observation_provider=lambda _session: observations.pop(0)),
        step_policy_agent=StepPolicyAgent(step_policy=decide),
        executor_agent=ExecutorAgent(adapter),
        verifier_agent=VerifierAgent(),
        recovery_agent=RecoveryAgent(),
    )
    completed = runtime.run(
        runtime.create_session(
            "Tap the target.",
            target_kind=EntityKind.TASK,
            target_id="tap_complete",
            waypoint_sequence=_sequence(),
        )
    )

    assert completed.current_step is not None
    assert "mobile.tap" in completed.current_step.allowed_side_effects
    assert AgentRole.EXECUTOR in [result.role for result in completed.role_results]
    assert completed.last_execution_result is not None
    assert completed.last_execution_result.state == GovernedActionState.EXECUTED
    assert [proposal.action_tool_name for proposal in adapter.submitted_proposals] == ["mobile.tap"]


def test_waypoint_empty_actions_block_mobile_action_execution() -> None:
    adapter = FakePlatformAdapter()
    runtime = TaskGraphRuntime(
        observer_agent=ObserverAgent(
            observation_provider=lambda _session: _observation("observation:ready", "ready")
        ),
        step_policy_agent=StepPolicyAgent(
            step_policy=lambda _session: StepDecision(
                decision_id="decision:blocked-tap",
                decision_type=StepDecisionType.PROPOSE_EXECUTION,
                summary="Try to tap the target.",
                proposal=_tap_proposal(),
            )
        ),
        executor_agent=ExecutorAgent(adapter),
        verifier_agent=VerifierAgent(),
        recovery_agent=RecoveryAgent(),
    )
    completed = runtime.run(
        runtime.create_session(
            "Tap the target.",
            target_kind=EntityKind.TASK,
            target_id="tap_complete",
            waypoint_sequence=_sequence(allowed_actions=[]),
        )
    )

    assert completed.current_step is not None
    assert completed.current_step.allowed_side_effects == []
    assert AgentRole.EXECUTOR not in [result.role for result in completed.role_results]
    assert completed.last_execution_result is None
    assert adapter.submitted_proposals == []
