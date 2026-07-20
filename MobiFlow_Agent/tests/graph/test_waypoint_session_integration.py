from mobiflow_agent.agents.contracts import StepDecision, StepDecisionType
from mobiflow_agent.agents.observer import ObserverAgent
from mobiflow_agent.agents.recovery import RecoveryAgent
from mobiflow_agent.agents.step_policy import StepPolicyAgent
from mobiflow_agent.agents.verifier import VerifierAgent
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
from mobiflow_agent.task.plan import TaskStatus
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


# ---------------------------------------------------------------------------
# E2E: injected waypoint sequence runs and bypasses planner
# ---------------------------------------------------------------------------

def _arrival_spec_e2e(waypoint_id: str) -> VerificationSpec:
    """Arrival spec whose evidence_hint matches the e2e observation's searchable text."""
    return VerificationSpec(
        verification_id=f"verification:{waypoint_id}",
        target_kind=EntityKind.TASK,
        target_id=waypoint_id,
        success_checks=[
            VerificationCheck(
                check_id=f"{waypoint_id}-check",
                description="Waypoint reached.",
                # "message_sent" appears in the observation fact value, so the
                # default VerifierAgent will find it in searchable_text and
                # count this check as matched.
                evidence_hint=waypoint_id,
            )
        ],
    )


def _single_sequence() -> WaypointSequence:
    return WaypointSequence(
        sequence_id="wechat.text_chat.v1",
        behavior_label="wechat_text_chat",
        profile_package="com.tencent.mm",
        waypoints=[
            Waypoint(
                waypoint_id="message_sent",
                description="Send a text message.",
                arrival_spec=_arrival_spec_e2e("message_sent"),
            )
        ],
    )


def test_run_executes_injected_waypoint_sequence_skipping_planner():
    """
    Inject a WaypointSequence into create_session, call run(), and assert that:
    - plan.behavior_label == "wechat_text_chat"  (planner was bypassed — planner
      products have no behavior_label)
    - plan.steps contains exactly the waypoint id
    - current_step.step_id == waypoint id  (runtime executed that step)
    - status == COMPLETED
    """

    def observe(_session):
        # The fact value contains "message_sent", so evidence_hint="message_sent"
        # in _arrival_spec_e2e will match via searchable_text.
        # EvidenceRef is required for the verifier to set evidence_refs != [] and
        # reach the VERIFIED_SUCCESS branch (line 255 in verifier.py).
        return ObservationView(
            observation_id="obs-e2e-1",
            focus_kind=EntityKind.TASK,
            focus_id="message_sent",
            facts=[
                ObservationFact(
                    fact_id="mobile_observation_summary",
                    source=ObservationFactSource.PLATFORM,
                    title="Mobile observation summary",
                    value={"waypoint_id": "message_sent", "status": "arrived"},
                    evidence_refs=[
                        EvidenceRef(
                            evidence_id="evidence:message_sent",
                            kind=EvidenceKind.PLATFORM_SNAPSHOT,
                            summary="Waypoint message_sent reached.",
                            locator="message_sent",
                        )
                    ],
                )
            ],
        )

    def decide(_session):
        return StepDecision(
            decision_id="d-e2e-1",
            decision_type=StepDecisionType.STEP_SUCCEEDED,
            summary="Message sent; waypoint reached.",
        )

    runtime = TaskGraphRuntime(
        observer_agent=ObserverAgent(observation_provider=observe),
        step_policy_agent=StepPolicyAgent(step_policy=decide),
        verifier_agent=VerifierAgent(),
        recovery_agent=RecoveryAgent(),
    )

    session = runtime.create_session(
        "Collect wechat text chat traffic.",
        target_kind=EntityKind.TASK,
        target_id="message_sent",
        waypoint_sequence=_single_sequence(),
    )
    completed = runtime.run(session)

    # planner was skipped: plan is still the compiled waypoint product
    assert completed.plan is not None
    assert completed.plan.behavior_label == "wechat_text_chat"
    assert [s.step_id for s in completed.plan.steps] == ["message_sent"]
    # runtime executed the waypoint step
    assert completed.current_step is not None
    assert completed.current_step.step_id == "message_sent"
    assert completed.status == TaskStatus.COMPLETED
