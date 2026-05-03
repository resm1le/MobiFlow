from mobiflow_agent.agents.contracts import AgentRole, RecoveryOutcome
from mobiflow_agent.agents.executor import ExecutorAgent
from mobiflow_agent.agents.observer import ObserverAgent
from mobiflow_agent.agents.recovery import RecoveryAgent
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
    VerificationStatus,
)
from mobiflow_agent.control.policy import TaskControlPolicy
from mobiflow_agent.control.orchestrator import TaskOrchestratorService
from mobiflow_agent.evaluation.scenario.fixtures import login_success_case, wrong_button_no_success_case
from mobiflow_agent.model import ModelProfile, ModelRegistry, RoleModelPolicy
from mobiflow_agent.model.providers import NoopModelClient
from mobiflow_agent.platform.adapter import FakePlatformAdapter
from mobiflow_agent.platform.simulation import SimulatedMobilePlatformAdapter
from mobiflow_agent.platform.types import GovernedActionResult, GovernedActionState
from mobiflow_agent.runtime.state import RuntimeLifecycle
from mobiflow_agent.task.completion import TaskCompletionVerdict
from mobiflow_agent.task.plan import TaskStatus


def _build_observation(observation_id: str, run_id: str, *, status: str = "cancelled") -> ObservationView:
    return ObservationView(
        observation_id=observation_id,
        focus_kind=EntityKind.RUN,
        focus_id=run_id,
        facts=[
            ObservationFact(
                fact_id=f"fact:{observation_id}",
                source=ObservationFactSource.PLATFORM,
                title="Run observation",
                value={"run_id": run_id, "status": status},
                evidence_refs=[
                    EvidenceRef(
                        evidence_id=f"evidence:{observation_id}",
                        kind=EvidenceKind.PLATFORM_SNAPSHOT,
                        summary=f"Observed run state: {status}.",
                        locator=run_id,
                    )
                ],
            )
        ],
    )


def _proposal() -> ExecutionProposal:
    return ExecutionProposal(
        proposal_id="proposal-1",
        action_tool_name="cancel_run",
        arguments={"runId": "run-123"},
        target_kind=EntityKind.RUN,
        target_id="run-123",
        rationale="Cancel the blocked run.",
    )


def _verification_spec(*, evidence_hint: str = "cancelled") -> VerificationSpec:
    return VerificationSpec(
        verification_id="verification:run:run-123",
        target_kind=EntityKind.RUN,
        target_id="run-123",
        success_checks=[
            VerificationCheck(
                check_id=f"run-{evidence_hint}",
                description=f"The run reaches {evidence_hint} status.",
                evidence_hint=evidence_hint,
            )
        ],
    )


def test_task_orchestrator_service_completes_multi_step_task_chain() -> None:
    adapter = FakePlatformAdapter(
        submit_results=[
            GovernedActionResult(
                state=GovernedActionState.EXECUTED,
                proposal_id="proposal-1",
                action_tool_name="cancel_run",
                result={"ok": True},
            )
        ]
    )
    observations = [
        _build_observation("observe-1", "run-123", status="blocked"),
        _build_observation("observe-2", "run-123", status="cancelled"),
    ]

    def observe(_session):
        return observations.pop(0)

    orchestrator = TaskOrchestratorService(
        observer_agent=ObserverAgent(observation_provider=observe),
        executor_agent=ExecutorAgent(adapter),
        verifier_agent=VerifierAgent(),
        recovery_agent=RecoveryAgent(),
    )

    session = orchestrator.create_session(
        "Cancel the blocked run",
        target_kind=EntityKind.RUN,
        target_id="run-123",
        proposal=_proposal(),
        verification_spec=_verification_spec(),
    )
    completed = orchestrator.run(session)

    assert completed.status == TaskStatus.COMPLETED
    assert completed.completion_verdict == TaskCompletionVerdict.TASK_COMPLETED
    assert completed.current_step is not None
    assert completed.current_step.kind.value == "dynamic"
    assert completed.last_verdict is not None
    assert completed.last_verdict.status == VerificationStatus.VERIFIED_SUCCESS
    assert [request.role for request in completed.role_requests] == [
        AgentRole.PLANNER,
        AgentRole.OBSERVER,
        AgentRole.STEP_POLICY,
        AgentRole.EXECUTOR,
        AgentRole.OBSERVER,
        AgentRole.STEP_POLICY,
        AgentRole.VERIFIER,
    ]
    assert [result.role for result in completed.role_results] == [
        AgentRole.PLANNER,
        AgentRole.OBSERVER,
        AgentRole.STEP_POLICY,
        AgentRole.EXECUTOR,
        AgentRole.OBSERVER,
        AgentRole.STEP_POLICY,
        AgentRole.VERIFIER,
    ]
    assert [result.next_role for result in completed.role_results] == [
        AgentRole.OBSERVER,
        AgentRole.STEP_POLICY,
        AgentRole.EXECUTOR,
        AgentRole.OBSERVER,
        AgentRole.STEP_POLICY,
        AgentRole.VERIFIER,
        None,
    ]
    assert completed.status_history == [
        TaskStatus.CREATED,
        TaskStatus.PLANNING,
        TaskStatus.OBSERVING,
        TaskStatus.EXECUTING,
        TaskStatus.OBSERVING,
        TaskStatus.VERIFYING,
        TaskStatus.COMPLETED,
    ]


def test_task_orchestrator_service_completes_observe_verify_chain() -> None:
    observations = [_build_observation("observe-1", "run-123", status="healthy")]

    def observe(_session):
        return observations.pop(0)

    orchestrator = TaskOrchestratorService(
        observer_agent=ObserverAgent(observation_provider=observe),
        verifier_agent=VerifierAgent(),
        recovery_agent=RecoveryAgent(),
    )

    session = orchestrator.create_session(
        "Inspect blocked task",
        target_kind=EntityKind.RUN,
        target_id="run-123",
    )
    completed = orchestrator.run(session)

    assert completed.status == TaskStatus.COMPLETED
    assert completed.completion_verdict == TaskCompletionVerdict.TASK_COMPLETED
    assert [request.role for request in completed.role_requests] == [
        AgentRole.PLANNER,
        AgentRole.OBSERVER,
        AgentRole.STEP_POLICY,
        AgentRole.VERIFIER,
    ]
    assert completed.status_history == [
        TaskStatus.CREATED,
        TaskStatus.PLANNING,
        TaskStatus.OBSERVING,
        TaskStatus.VERIFYING,
        TaskStatus.COMPLETED,
    ]


def test_task_orchestrator_service_pauses_for_approval_and_resumes_to_completion() -> None:
    adapter = FakePlatformAdapter(
        submit_results=[
            GovernedActionResult(
                state=GovernedActionState.APPROVAL_REQUIRED,
                proposal_id="proposal-1",
                action_tool_name="cancel_run",
                confirmation_id="confirm-1",
                confirmation_summary="Approve the cancel action.",
            )
        ],
        resolve_results=[
            GovernedActionResult(
                state=GovernedActionState.EXECUTED,
                proposal_id="proposal-1",
                action_tool_name="cancel_run",
                result={"ok": True},
            )
        ],
    )
    observations = [
        _build_observation("observe-1", "run-123", status="blocked"),
        _build_observation("observe-2", "run-123", status="cancelled"),
    ]

    def observe(_session):
        return observations.pop(0)

    orchestrator = TaskOrchestratorService(
        observer_agent=ObserverAgent(observation_provider=observe),
        executor_agent=ExecutorAgent(adapter),
        verifier_agent=VerifierAgent(),
        recovery_agent=RecoveryAgent(),
    )

    session = orchestrator.create_session(
        "Cancel the blocked run",
        target_kind=EntityKind.RUN,
        target_id="run-123",
        proposal=_proposal(),
        verification_spec=_verification_spec(),
    )
    paused = orchestrator.run(session)

    assert paused.status == TaskStatus.AWAITING_APPROVAL
    assert paused.completion_verdict == TaskCompletionVerdict.BLOCKED
    assert paused.pending_execution is not None
    assert paused.pending_execution.confirmation_id == "confirm-1"

    resumed = orchestrator.resume(paused, approved=True)

    assert resumed.status == TaskStatus.COMPLETED
    assert resumed.completion_verdict == TaskCompletionVerdict.TASK_COMPLETED
    assert resumed.pending_execution is None
    assert resumed.last_verdict is not None
    assert resumed.last_verdict.status == VerificationStatus.VERIFIED_SUCCESS
    assert resumed.status_history == [
        TaskStatus.CREATED,
        TaskStatus.PLANNING,
        TaskStatus.OBSERVING,
        TaskStatus.EXECUTING,
        TaskStatus.AWAITING_APPROVAL,
        TaskStatus.EXECUTING,
        TaskStatus.OBSERVING,
        TaskStatus.VERIFYING,
        TaskStatus.COMPLETED,
    ]


def test_task_orchestrator_service_routes_rejected_approval_to_recovery_then_verify() -> None:
    adapter = FakePlatformAdapter(
        submit_results=[
            GovernedActionResult(
                state=GovernedActionState.APPROVAL_REQUIRED,
                proposal_id="proposal-1",
                action_tool_name="cancel_run",
                confirmation_id="confirm-1",
                confirmation_summary="Approve the cancel action.",
            )
        ]
    )
    observations = [_build_observation("observe-1", "run-123", status="blocked")]

    def observe(_session):
        return observations.pop(0)

    def recovery_outcome(session, failure_verdict):
        return RecoveryOutcome(
            summary="Recovery could not restore progress after approval was rejected.",
            target_kind=failure_verdict.target_kind,
            target_id=failure_verdict.target_id,
            evidence_refs=[
                EvidenceRef(
                    evidence_id=f"recovery-note:{session.session_id}",
                    kind=EvidenceKind.INLINE_NOTE,
                    summary="Approval rejection left the task unresolved.",
                    locator=session.session_id,
                )
            ],
        )

    orchestrator = TaskOrchestratorService(
        observer_agent=ObserverAgent(observation_provider=observe),
        executor_agent=ExecutorAgent(adapter),
        verifier_agent=VerifierAgent(),
        recovery_agent=RecoveryAgent(recovery=recovery_outcome),
    )

    session = orchestrator.create_session(
        "Cancel the blocked run",
        target_kind=EntityKind.RUN,
        target_id="run-123",
        proposal=_proposal(),
        verification_spec=_verification_spec(),
    )
    paused = orchestrator.run(session)
    failed = orchestrator.resume(paused, approved=False)

    assert failed.status == TaskStatus.FAILED
    assert failed.last_verdict is not None
    assert failed.last_verdict.status == VerificationStatus.VERIFIED_FAILED
    assert [result.role for result in failed.role_results][-2:] == [AgentRole.RECOVERY, AgentRole.VERIFIER]
    assert failed.status_history[-3:] == [
        TaskStatus.RECOVERING,
        TaskStatus.VERIFYING,
        TaskStatus.FAILED,
    ]


def test_task_orchestrator_service_updates_memory_and_evaluation_support_contexts_per_step() -> None:
    observations = [_build_observation("observe-1", "run-123", status="healthy")]
    support_calls: list[tuple[str, TaskStatus]] = []

    def observe(_session):
        return observations.pop(0)

    def memory_support(session):
        support_calls.append(("memory", session.status))
        return {"step_kind": session.current_step.kind.value, "step_id": session.current_step.step_id}

    def evaluation_support(session):
        support_calls.append(("evaluation", session.status))
        return {"verdict_status": session.last_verdict.status.value, "target_id": session.last_verdict.target_id}

    orchestrator = TaskOrchestratorService(
        observer_agent=ObserverAgent(observation_provider=observe),
        verifier_agent=VerifierAgent(),
        recovery_agent=RecoveryAgent(),
        memory_support=memory_support,
        evaluation_support=evaluation_support,
    )

    session = orchestrator.create_session(
        "Inspect blocked task",
        target_kind=EntityKind.RUN,
        target_id="run-123",
    )
    completed = orchestrator.run(session)

    assert completed.status == TaskStatus.COMPLETED
    assert len(completed.memory_context) == 1
    assert len(completed.evaluation_context) == 1
    step_payloads = list(completed.memory_context.values())
    assert [payload["step_kind"] for payload in step_payloads] == ["dynamic"]
    assert list(completed.evaluation_context.values()) == [
        {
            "verdict_status": VerificationStatus.VERIFIED_SUCCESS.value,
            "target_id": "run-123",
        }
    ]
    assert ("memory", TaskStatus.PLANNING) in support_calls
    assert ("evaluation", TaskStatus.VERIFYING) in support_calls


def test_task_orchestrator_service_runtime_projection_roundtrips_waiting_and_verifying_state() -> None:
    adapter = FakePlatformAdapter(
        submit_results=[
            GovernedActionResult(
                state=GovernedActionState.APPROVAL_REQUIRED,
                proposal_id="proposal-1",
                action_tool_name="cancel_run",
                confirmation_id="confirm-1",
                confirmation_summary="Approve the cancel action.",
            )
        ]
    )
    observations = [_build_observation("observe-1", "run-123", status="blocked")]

    def observe(_session):
        return observations.pop(0)

    orchestrator = TaskOrchestratorService(
        observer_agent=ObserverAgent(observation_provider=observe),
        executor_agent=ExecutorAgent(adapter),
        verifier_agent=VerifierAgent(),
        recovery_agent=RecoveryAgent(),
    )

    session = orchestrator.create_session(
        "Cancel the blocked run",
        target_kind=EntityKind.RUN,
        target_id="run-123",
        proposal=_proposal(),
        verification_spec=_verification_spec(),
    )
    paused = orchestrator.run(session)
    runtime_state = orchestrator.export_runtime_state(paused)

    assert runtime_state.lifecycle == RuntimeLifecycle.AWAITING_APPROVAL
    assert runtime_state.pending_execution is not None
    assert runtime_state.pending_execution.confirmation_id == "confirm-1"

    restored = orchestrator.apply_runtime_state(
        paused.model_copy(
            deep=True,
            update={
                "status": TaskStatus.CREATED,
                "status_history": [TaskStatus.CREATED],
                "pending_execution": None,
                "active_verification_spec": None,
            },
        ),
        runtime_state,
    )
    assert restored.status == TaskStatus.AWAITING_APPROVAL
    assert restored.pending_execution is not None
    assert restored.pending_execution.confirmation_id == "confirm-1"

    verifying_state = runtime_state.model_copy(
        update={
            "lifecycle": RuntimeLifecycle.VERIFYING,
            "active_verification": paused.plan.steps[-1].verification_spec,
        }
    )
    verifying = orchestrator.apply_runtime_state(paused.model_copy(deep=True), verifying_state)
    assert verifying.status == TaskStatus.VERIFYING
    assert verifying.active_verification_spec is not None
    assert verifying.active_verification_spec.verification_id.startswith("verification:")


def test_task_orchestrator_service_records_model_trace_and_role_profiles() -> None:
    observations = [_build_observation("observe-1", "run-123", status="healthy")]

    def observe(_session):
        return observations.pop(0)

    model_client = NoopModelClient(
        responses=[
            {
                "contract": {
                    "contract_id": "contract-1",
                    "user_goal": "Inspect blocked task",
                    "outcome": "Inspect blocked task safely",
                    "target_kind": "run",
                    "target_id": "run-123",
                    "success_criteria": [
                        {
                            "criterion_id": "primary",
                            "description": "Finish with evidence-backed verification.",
                        }
                    ],
                    "verification_focus": ["evidence", "task-progress"],
                    "approval_mode": "on_risk",
                },
                "plan": {
                    "plan_id": "plan-1",
                    "summary": "Dynamic observe and verify",
                    "steps": [
                        {
                            "step_id": "step-1",
                            "kind": "dynamic",
                            "goal": "Reach a healthy run state and verify evidence.",
                            "expected_outputs": ["observation", "step_decision", "verification_verdict"],
                            "verification_target_kind": "run",
                            "verification_target_id": "run-123",
                            "allowed_side_effects": ["cancel_run"],
                            "verification_spec": {
                                "verification_id": "verification:run:run-123",
                                "target_kind": "run",
                                "target_id": "run-123",
                                "success_checks": [
                                    {
                                        "check_id": "run-healthy",
                                        "description": "The run stays healthy.",
                                        "evidence_hint": "healthy",
                                    }
                                ],
                            },
                            "policy": {
                                "policy_id": "policy-1",
                                "description": "Observe healthy state, then verify.",
                            },
                        },
                    ],
                },
            },
            {
                "summary": "Evidence confirms the run is healthy.",
                "matched_check_ids": ["run-healthy"],
            },
        ]
    )
    orchestrator = TaskOrchestratorService(
        observer_agent=ObserverAgent(observation_provider=observe),
        verifier_agent=VerifierAgent(),
        recovery_agent=RecoveryAgent(),
        model_registry=ModelRegistry(
            profiles=[
                ModelProfile(name="planner-profile", provider="noop", model="noop-model"),
                ModelProfile(name="verifier-profile", provider="noop", model="noop-model"),
            ],
            clients={"noop": model_client},
        ),
        role_model_policy=RoleModelPolicy(
            role_profiles={
                AgentRole.PLANNER.value: "planner-profile",
                AgentRole.VERIFIER.value: "verifier-profile",
            }
        ),
    )

    session = orchestrator.create_session(
        "Inspect blocked task",
        target_kind=EntityKind.RUN,
        target_id="run-123",
    )
    completed = orchestrator.run(session)

    assert completed.status == TaskStatus.COMPLETED
    assert len(completed.model_trace) == 1
    assert [trace.profile_name for trace in completed.model_trace] == ["planner-profile"]
    assert completed.role_requests[0].payload["active_model_profile"] == "planner-profile"
    assert completed.role_requests[-1].role == AgentRole.VERIFIER


def test_task_orchestrator_service_builds_session_digest_and_handoff_roundtrip() -> None:
    observations = [_build_observation("observe-1", "run-123", status="healthy")]

    def observe(_session):
        return observations.pop(0)

    orchestrator = TaskOrchestratorService(
        observer_agent=ObserverAgent(observation_provider=observe),
        verifier_agent=VerifierAgent(),
        recovery_agent=RecoveryAgent(),
    )

    completed = orchestrator.run(
        orchestrator.create_session(
            "Inspect blocked task",
            target_kind=EntityKind.RUN,
            target_id="run-123",
        )
    )
    handoff = orchestrator.export_context_handoff(completed)
    resumed = orchestrator.create_session(
        "Inspect blocked task",
        target_kind=EntityKind.RUN,
        target_id="run-123",
        handoff=handoff,
    )

    assert completed.session_digest is not None
    assert completed.step_summaries
    assert handoff.source_session_id == completed.session_id
    assert resumed.imported_handoff is not None
    assert resumed.session_digest is not None


def test_task_orchestrator_service_runs_against_simulated_platform_chain() -> None:
    case = login_success_case()
    adapter = SimulatedMobilePlatformAdapter(case.platform_scenario, target_id=case.scenario_id)
    request = case.requests[0]

    orchestrator = TaskOrchestratorService(
        observer_agent=ObserverAgent(adapter=adapter),
        executor_agent=ExecutorAgent(adapter),
        verifier_agent=VerifierAgent(),
        recovery_agent=RecoveryAgent(),
        policy=TaskControlPolicy(allow_recovery=False),
    )

    completed = orchestrator.run(
        orchestrator.create_session(
            request.goal,
            target_kind=request.target_kind,
            target_id=request.target_id,
            proposal=request.proposal,
            verification_spec=request.verification_spec,
        )
    )

    assert completed.status == TaskStatus.COMPLETED
    assert completed.last_verdict is not None
    assert completed.last_verdict.status == VerificationStatus.VERIFIED_SUCCESS
    assert completed.last_observation is not None
    assert "simulated_screen_snapshot" in [fact.fact_id for fact in completed.last_observation.facts]
    assert adapter.action_traces[-1].action_tool_name == "mobile.launch"


def test_task_orchestrator_service_does_not_mark_success_without_matching_simulated_evidence() -> None:
    case = wrong_button_no_success_case()
    scenario = case.platform_scenario.model_copy(update={"initial_screen_id": "login_blank"})
    adapter = SimulatedMobilePlatformAdapter(scenario, target_id=case.scenario_id)
    request = case.requests[1]

    orchestrator = TaskOrchestratorService(
        observer_agent=ObserverAgent(adapter=adapter),
        executor_agent=ExecutorAgent(adapter),
        verifier_agent=VerifierAgent(),
        recovery_agent=RecoveryAgent(),
        policy=TaskControlPolicy(allow_recovery=False),
    )

    completed = orchestrator.run(
        orchestrator.create_session(
            request.goal,
            target_kind=request.target_kind,
            target_id=request.target_id,
            proposal=request.proposal,
            verification_spec=request.verification_spec,
        )
    )

    assert completed.status == TaskStatus.FAILED
    assert completed.completion_verdict == TaskCompletionVerdict.FAILED
    assert completed.last_verdict is not None
    assert completed.last_verdict.status == VerificationStatus.VERIFIED_FAILED
