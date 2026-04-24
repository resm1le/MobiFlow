from mobiflow_agent.agents import AgentRole
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
    VerificationStatus,
)
from mobiflow_agent.model import ModelProfile, ModelRegistry, ModelRuntime, RoleModelPolicy
from mobiflow_agent.model.providers import NoopModelClient
from mobiflow_agent.task.plan import TaskPlan, TaskStep, TaskStepKind
from mobiflow_agent.task.session import TaskSession


def _session_with_verification_spec(spec: VerificationSpec) -> TaskSession:
    step = TaskStep(
        step_id="step-1",
        kind=TaskStepKind.VERIFY,
        goal="Verify the run outcome",
        expected_outputs=["verification_verdict"],
        verification_target_kind=spec.target_kind,
        verification_target_id=spec.target_id,
        verification_spec=spec,
    )
    return TaskSession(
        session_id="task-session-1",
        goal="Verify the run outcome",
        target_kind=spec.target_kind,
        target_id=spec.target_id,
        plan=TaskPlan(plan_id="plan-1", summary="verification plan", steps=[step]),
        current_step_index=0,
        current_step=step,
    )


def test_verifier_agent_matches_verification_spec_checks_from_observation_text() -> None:
    spec = VerificationSpec(
        verification_id="verification:run-123",
        target_kind=EntityKind.RUN,
        target_id="run-123",
        success_checks=[
            VerificationCheck(
                check_id="run-cancelled",
                description="The run reaches cancelled status.",
                evidence_hint="cancelled",
            )
        ],
    )
    session = _session_with_verification_spec(spec)
    observation = ObservationView(
        observation_id="observe-1",
        focus_kind=EntityKind.RUN,
        focus_id="run-123",
        facts=[
            ObservationFact(
                fact_id="fact-1",
                source=ObservationFactSource.PLATFORM,
                title="Run status",
                value={"status": "cancelled"},
                evidence_refs=[
                    EvidenceRef(
                        evidence_id="evidence-1",
                        kind=EvidenceKind.PLATFORM_SNAPSHOT,
                        summary="Run was cancelled.",
                        locator="run-123",
                    )
                ],
            )
        ],
    )

    verdict, role_result = VerifierAgent().verify(session, observation)

    assert verdict.status == VerificationStatus.VERIFIED_SUCCESS
    assert verdict.matched_check_ids == ["run-cancelled"]
    assert role_result.next_role is None


def test_verifier_agent_returns_blocked_when_observation_matches_blocked_condition() -> None:
    spec = VerificationSpec(
        verification_id="verification:run-123",
        target_kind=EntityKind.RUN,
        target_id="run-123",
        success_checks=[
            VerificationCheck(
                check_id="run-cancelled",
                description="The run reaches cancelled status.",
                evidence_hint="cancelled",
            )
        ],
        blocked_conditions=["approval pending"],
    )
    session = _session_with_verification_spec(spec)
    observation = ObservationView(
        observation_id="observe-2",
        focus_kind=EntityKind.RUN,
        focus_id="run-123",
        facts=[
            ObservationFact(
                fact_id="fact-2",
                source=ObservationFactSource.PLATFORM,
                title="Approval state",
                value={"state": "approval pending"},
                evidence_refs=[
                    EvidenceRef(
                        evidence_id="evidence-2",
                        kind=EvidenceKind.PLATFORM_SNAPSHOT,
                        summary="Approval is still pending.",
                        locator="run-123",
                    )
                ],
            )
        ],
    )

    verdict, role_result = VerifierAgent().verify(session, observation)

    assert verdict.status == VerificationStatus.BLOCKED
    assert verdict.blocked_reason == "approval pending"
    assert verdict.unmatched_check_ids == ["run-cancelled"]
    assert role_result.next_role == AgentRole.RECOVERY


def test_verifier_agent_model_interpretation_cannot_override_missing_evidence() -> None:
    spec = VerificationSpec(
        verification_id="verification:run-123",
        target_kind=EntityKind.RUN,
        target_id="run-123",
        success_checks=[
            VerificationCheck(
                check_id="run-cancelled",
                description="The run reaches cancelled status.",
                evidence_hint="cancelled",
            )
        ],
    )
    session = _session_with_verification_spec(spec).model_copy(update={"active_model_profile": "verifier-profile"})
    runtime = ModelRuntime(
        ModelRegistry(
            profiles=[ModelProfile(name="verifier-profile", provider="noop", model="noop-model")],
            clients={
                "noop": NoopModelClient(
                    responses=[
                        {
                            "summary": "The run looks cancelled and successful.",
                            "matched_check_ids": ["run-cancelled"],
                        }
                    ]
                )
            },
        ),
        role_policy=RoleModelPolicy(role_profiles={AgentRole.VERIFIER.value: "verifier-profile"}),
    )

    verdict, role_result = VerifierAgent(model_client=runtime).verify(session, None)

    assert verdict.status == VerificationStatus.VERIFIED_UNKNOWN
    assert verdict.unmatched_check_ids == ["run-cancelled"]
    assert role_result.payload["model_trace_refs"]
    assert len(session.model_trace) == 1
