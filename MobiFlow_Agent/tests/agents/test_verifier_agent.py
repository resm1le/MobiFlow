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
    VerificationDiagnostics,
    VerificationPredicate,
    VerificationPredicateOperator,
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


def test_verifier_agent_matches_structured_predicates_before_text_fallback() -> None:
    spec = VerificationSpec(
        verification_id="verification:screen-home",
        target_kind=EntityKind.TASK,
        target_id="task-1",
        success_checks=[
            VerificationCheck(
                check_id="home-screen-visible",
                description="The home screen is visible.",
                evidence_hint="text that is intentionally absent",
                predicates=[
                    VerificationPredicate(
                        fact_id="simulated_screen_snapshot",
                        field_path="value.title",
                        operator=VerificationPredicateOperator.EQUALS,
                        expected="Home Screen",
                    ),
                    VerificationPredicate(
                        fact_id="simulated_ui_tree",
                        field_path="value[].node_id",
                        operator=VerificationPredicateOperator.ANY_EQUALS,
                        expected="home_title",
                    ),
                ],
            )
        ],
    )
    session = _session_with_verification_spec(spec)
    observation = ObservationView(
        observation_id="observe-home",
        focus_kind=EntityKind.TASK,
        focus_id="task-1",
        facts=[
            ObservationFact(
                fact_id="simulated_screen_snapshot",
                source=ObservationFactSource.PLATFORM,
                title="Screen",
                value={"screen_id": "home", "title": "Home Screen"},
                evidence_refs=[
                    EvidenceRef(
                        evidence_id="screen-evidence",
                        kind=EvidenceKind.PLATFORM_SNAPSHOT,
                        summary="Screen evidence.",
                        locator="home",
                    )
                ],
            ),
            ObservationFact(
                fact_id="simulated_ui_tree",
                source=ObservationFactSource.PLATFORM,
                title="Tree",
                value=[{"node_id": "home_title", "text": "Welcome"}],
                evidence_refs=[
                    EvidenceRef(
                        evidence_id="tree-evidence",
                        kind=EvidenceKind.ARTIFACT,
                        summary="Tree evidence.",
                        locator="home",
                    )
                ],
            ),
        ],
    )

    verdict, _ = VerifierAgent().verify(session, observation)

    assert verdict.status == VerificationStatus.VERIFIED_SUCCESS
    assert verdict.matched_check_ids == ["home-screen-visible"]


def test_verifier_agent_returns_unknown_when_structured_predicate_lacks_evidence_match() -> None:
    spec = VerificationSpec(
        verification_id="verification:screen-home",
        target_kind=EntityKind.TASK,
        target_id="task-1",
        success_checks=[
            VerificationCheck(
                check_id="home-screen-visible",
                description="The home screen is visible.",
                evidence_hint="Home Screen",
                predicates=[
                    VerificationPredicate(
                        fact_id="simulated_screen_snapshot",
                        field_path="value.title",
                        operator=VerificationPredicateOperator.EQUALS,
                        expected="Home Screen",
                    )
                ],
            )
        ],
    )
    session = _session_with_verification_spec(spec)
    observation = ObservationView(
        observation_id="observe-loading",
        focus_kind=EntityKind.TASK,
        focus_id="task-1",
        facts=[
            ObservationFact(
                fact_id="simulated_screen_snapshot",
                source=ObservationFactSource.PLATFORM,
                title="Screen",
                value={"screen_id": "loading", "title": "Loading Screen"},
                evidence_refs=[
                    EvidenceRef(
                        evidence_id="screen-evidence",
                        kind=EvidenceKind.PLATFORM_SNAPSHOT,
                        summary="Screen evidence.",
                        locator="loading",
                    )
                ],
            )
        ],
    )

    verdict, _ = VerifierAgent().verify(session, observation)

    assert verdict.status == VerificationStatus.VERIFIED_UNKNOWN
    assert verdict.unmatched_check_ids == ["home-screen-visible"]


def test_verifier_agent_matches_structured_blocked_predicate_before_success() -> None:
    spec = VerificationSpec(
        verification_id="verification:permission-dialog",
        target_kind=EntityKind.TASK,
        target_id="task-1",
        success_checks=[
            VerificationCheck(
                check_id="home-screen-visible",
                description="Home Screen is visible.",
                evidence_hint="Home Screen",
            )
        ],
        blocked_checks=[
            VerificationCheck(
                check_id="permission-dialog",
                description="Permission dialog blocks progress.",
                predicates=[
                    VerificationPredicate(
                        fact_id="simulated_screen_snapshot",
                        field_path="value.title",
                        operator=VerificationPredicateOperator.EQUALS,
                        expected="Permission Dialog",
                    )
                ],
            )
        ],
    )
    session = _session_with_verification_spec(spec)
    observation = ObservationView(
        observation_id="observe-permission",
        focus_kind=EntityKind.TASK,
        focus_id="task-1",
        facts=[
            ObservationFact(
                fact_id="simulated_screen_snapshot",
                source=ObservationFactSource.PLATFORM,
                title="Screen",
                value={"screen_id": "permission", "title": "Permission Dialog"},
                evidence_refs=[
                    EvidenceRef(
                        evidence_id="permission-evidence",
                        kind=EvidenceKind.PLATFORM_SNAPSHOT,
                        summary="Permission dialog is visible.",
                        locator="permission",
                    )
                ],
            )
        ],
    )

    verdict, _ = VerifierAgent().verify(session, observation)

    assert verdict.status == VerificationStatus.BLOCKED
    assert verdict.blocked_reason == "permission-dialog"
    assert isinstance(verdict.diagnostics, VerificationDiagnostics)
    assert verdict.diagnostics["suspected_current_state"] == "Permission Dialog"
    assert verdict.diagnostics["suggested_recovery_direction"] == "recover_or_handoff"


def test_verifier_agent_wrong_page_does_not_succeed_from_target_keyword_alone() -> None:
    spec = VerificationSpec(
        verification_id="verification:wrong-page",
        target_kind=EntityKind.TASK,
        target_id="task-1",
        success_checks=[
            VerificationCheck(
                check_id="home-node-visible",
                description="Home node is visible.",
                predicates=[
                    VerificationPredicate(
                        fact_id="simulated_ui_tree",
                        field_path="value[].node_id",
                        operator=VerificationPredicateOperator.ANY_EQUALS,
                        expected="home_title",
                    )
                ],
            )
        ],
        blocked_checks=[
            VerificationCheck(
                check_id="wrong-help-page",
                description="Help page is not the target page.",
                predicates=[
                    VerificationPredicate(
                        fact_id="simulated_screen_snapshot",
                        field_path="value.screen_id",
                        operator=VerificationPredicateOperator.EQUALS,
                        expected="help",
                    )
                ],
            )
        ],
    )
    session = _session_with_verification_spec(spec)
    observation = ObservationView(
        observation_id="observe-help",
        focus_kind=EntityKind.TASK,
        focus_id="task-1",
        facts=[
            ObservationFact(
                fact_id="simulated_screen_snapshot",
                source=ObservationFactSource.PLATFORM,
                title="Screen",
                value={"screen_id": "help", "title": "Help Screen", "note": "Home Screen docs"},
                evidence_refs=[
                    EvidenceRef(
                        evidence_id="help-evidence",
                        kind=EvidenceKind.PLATFORM_SNAPSHOT,
                        summary="Help page mentions Home Screen but is not home.",
                        locator="help",
                    )
                ],
            ),
            ObservationFact(
                fact_id="simulated_ui_tree",
                source=ObservationFactSource.PLATFORM,
                title="Tree",
                value=[{"node_id": "help_title", "text": "Home Screen help article"}],
                evidence_refs=[
                    EvidenceRef(
                        evidence_id="help-tree",
                        kind=EvidenceKind.ARTIFACT,
                        summary="Help tree.",
                        locator="help",
                    )
                ],
            ),
        ],
    )

    verdict, _ = VerifierAgent().verify(session, observation)

    assert verdict.status == VerificationStatus.BLOCKED
    assert verdict.blocked_reason == "wrong-help-page"
    assert verdict.matched_check_ids == []


def test_verifier_agent_loading_screen_returns_unknown_with_diagnostics() -> None:
    spec = VerificationSpec(
        verification_id="verification:loading",
        target_kind=EntityKind.TASK,
        target_id="task-1",
        success_checks=[
            VerificationCheck(
                check_id="home-screen-visible",
                description="Home Screen is visible.",
                predicates=[
                    VerificationPredicate(
                        fact_id="simulated_screen_snapshot",
                        field_path="value.title",
                        operator=VerificationPredicateOperator.EQUALS,
                        expected="Home Screen",
                    )
                ],
            )
        ],
    )
    session = _session_with_verification_spec(spec)
    observation = ObservationView(
        observation_id="observe-loading",
        focus_kind=EntityKind.TASK,
        focus_id="task-1",
        facts=[
            ObservationFact(
                fact_id="simulated_screen_snapshot",
                source=ObservationFactSource.PLATFORM,
                title="Screen",
                value={"screen_id": "loading", "title": "Loading Screen"},
                evidence_refs=[
                    EvidenceRef(
                        evidence_id="loading-evidence",
                        kind=EvidenceKind.PLATFORM_SNAPSHOT,
                        summary="Still loading.",
                        locator="loading",
                    )
                ],
            )
        ],
    )

    verdict, _ = VerifierAgent().verify(session, observation)

    assert verdict.status == VerificationStatus.VERIFIED_UNKNOWN
    assert verdict.diagnostics["suspected_current_state"] == "Loading Screen"
    assert verdict.diagnostics["suggested_recovery_direction"] == "observe_or_recover"
    assert verdict.model_dump(mode="json")["diagnostics"]["missing_evidence"] is False
