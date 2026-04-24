from mobiflow_agent.agents.contracts import (
    AgentRole,
    RecoveryOutcome,
    ReplanDecision,
    ReplanDecisionType,
    StepDecision,
    StepDecisionType,
)
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
    SuccessCriterion,
    TaskContract,
    VerificationCheck,
    VerificationSpec,
    VerificationStatus,
)
from mobiflow_agent.control import TaskOrchestratorService
from mobiflow_agent.control.orchestrator import TaskOrchestratorService as OrchestratorCompatImport
from mobiflow_agent.graph import TaskGraphRuntime, TaskGraphState
from mobiflow_agent.platform.adapter import FakePlatformAdapter
from mobiflow_agent.platform.types import GovernedActionResult, GovernedActionState
from mobiflow_agent.runtime import (
    InMemoryTaskHarnessStore,
    RuntimeCheckpointConfig,
    RuntimeCheckpointMode,
    TaskHarnessRequest,
    TaskHarnessService,
    TaskHarnessStatus,
    create_checkpointer,
)
from mobiflow_agent.task.completion import TaskCompletionVerdict
from mobiflow_agent.task.plan import TaskPlan, TaskStatus, TaskStep, TaskStepKind, TaskStepPolicy


def _build_observation(observation_id: str, run_id: str, *, status: str = "healthy") -> ObservationView:
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


def _verification_spec() -> VerificationSpec:
    return VerificationSpec(
        verification_id="verification:run:run-123",
        target_kind=EntityKind.RUN,
        target_id="run-123",
        success_checks=[
            VerificationCheck(
                check_id="run-healthy",
                description="The run is healthy.",
                evidence_hint="healthy",
            )
        ],
    )


def _step_decision(decision_type: StepDecisionType, suffix: str, **updates) -> StepDecision:
    data = {
        "decision_id": f"step-decision:{suffix}",
        "decision_type": decision_type,
        "summary": f"Decision {decision_type.value}.",
    }
    data.update(updates)
    return StepDecision.model_validate(data)


def test_task_graph_runtime_completes_observe_verify_chain() -> None:
    observations = [_build_observation("observe-1", "run-123", status="healthy")]

    def observe(_session):
        return observations.pop(0)

    runtime = TaskGraphRuntime(
        observer_agent=ObserverAgent(observation_provider=observe),
        verifier_agent=VerifierAgent(),
        recovery_agent=RecoveryAgent(),
    )

    completed = runtime.run(
        runtime.create_session(
            "Inspect blocked task",
            target_kind=EntityKind.RUN,
            target_id="run-123",
            verification_spec=_verification_spec(),
        )
    )

    assert completed.status == TaskStatus.COMPLETED
    assert completed.completion_verdict == TaskCompletionVerdict.TASK_COMPLETED
    assert completed.last_verdict is not None
    assert completed.last_verdict.status == VerificationStatus.VERIFIED_SUCCESS
    assert [request.role for request in completed.role_requests] == [
        AgentRole.PLANNER,
        AgentRole.OBSERVER,
        AgentRole.VERIFIER,
    ]
    assert completed.status_history == [
        TaskStatus.CREATED,
        TaskStatus.PLANNING,
        TaskStatus.OBSERVING,
        TaskStatus.VERIFYING,
        TaskStatus.COMPLETED,
    ]


def test_task_orchestrator_service_is_graph_backed_compatibility_name() -> None:
    orchestrator = TaskOrchestratorService()

    assert TaskOrchestratorService is OrchestratorCompatImport
    assert isinstance(orchestrator, TaskGraphRuntime)


def test_task_harness_service_defaults_to_graph_backed_orchestrator() -> None:
    harness = TaskHarnessService(store=InMemoryTaskHarnessStore())

    assert isinstance(harness._orchestrator, TaskGraphRuntime)


def test_task_graph_runtime_executes_governed_action_and_verifies() -> None:
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
        _build_observation("observe-2", "run-123", status="healthy"),
    ]

    def observe(_session):
        return observations.pop(0)

    runtime = TaskGraphRuntime(
        observer_agent=ObserverAgent(observation_provider=observe),
        executor_agent=ExecutorAgent(adapter),
        verifier_agent=VerifierAgent(),
        recovery_agent=RecoveryAgent(),
    )

    completed = runtime.run(
        runtime.create_session(
            "Cancel the blocked run",
            target_kind=EntityKind.RUN,
            target_id="run-123",
            proposal=_proposal(),
            verification_spec=_verification_spec(),
        )
    )

    assert completed.status == TaskStatus.COMPLETED
    assert completed.pending_execution is None
    assert completed.last_verdict is not None
    assert completed.last_verdict.status == VerificationStatus.VERIFIED_SUCCESS
    assert [result.role for result in completed.role_results] == [
        AgentRole.PLANNER,
        AgentRole.OBSERVER,
        AgentRole.EXECUTOR,
        AgentRole.OBSERVER,
        AgentRole.VERIFIER,
    ]


def test_task_graph_runtime_dynamic_step_succeeds_after_policy_decision() -> None:
    observations = [_build_observation("observe-1", "run-123", status="healthy")]

    runtime = TaskGraphRuntime(
        observer_agent=ObserverAgent(observation_provider=lambda _session: observations.pop(0)),
        step_policy_agent=StepPolicyAgent(
            step_policy=lambda _session: _step_decision(StepDecisionType.STEP_SUCCEEDED, "success")
        ),
        verifier_agent=VerifierAgent(),
        recovery_agent=RecoveryAgent(),
    )

    completed = runtime.run(
        runtime.create_session(
            "[dynamic] Inspect blocked task",
            target_kind=EntityKind.RUN,
            target_id="run-123",
            verification_spec=_verification_spec(),
        )
    )

    assert completed.status == TaskStatus.COMPLETED
    assert completed.current_step is not None
    assert completed.current_step.kind == TaskStepKind.DYNAMIC
    assert completed.step_policy_iterations[completed.current_step.step_id] == 1
    assert completed.last_step_decision is not None
    assert completed.last_step_decision.decision_type == StepDecisionType.STEP_SUCCEEDED
    assert [result.role for result in completed.role_results] == [
        AgentRole.PLANNER,
        AgentRole.OBSERVER,
        AgentRole.STEP_POLICY,
        AgentRole.VERIFIER,
    ]


def test_task_graph_runtime_dynamic_step_can_observe_again_before_success() -> None:
    observations = [
        _build_observation("observe-1", "run-123", status="blocked"),
        _build_observation("observe-2", "run-123", status="healthy"),
    ]

    def decide(session):
        if session.step_policy_iterations[session.current_step.step_id] == 1:
            return _step_decision(StepDecisionType.OBSERVE_AGAIN, "again")
        return _step_decision(StepDecisionType.STEP_SUCCEEDED, "success")

    runtime = TaskGraphRuntime(
        observer_agent=ObserverAgent(observation_provider=lambda _session: observations.pop(0)),
        step_policy_agent=StepPolicyAgent(step_policy=decide),
        verifier_agent=VerifierAgent(),
        recovery_agent=RecoveryAgent(),
    )

    completed = runtime.run(
        runtime.create_session(
            "[dynamic] Inspect blocked task",
            target_kind=EntityKind.RUN,
            target_id="run-123",
            verification_spec=_verification_spec(),
        )
    )

    assert completed.status == TaskStatus.COMPLETED
    assert completed.current_step is not None
    assert completed.step_policy_iterations[completed.current_step.step_id] == 2
    assert [decision.decision_type for decision in completed.step_decisions] == [
        StepDecisionType.OBSERVE_AGAIN,
        StepDecisionType.STEP_SUCCEEDED,
    ]


def test_task_graph_runtime_dynamic_step_max_iterations_routes_to_recovery() -> None:
    observations = [
        _build_observation("observe-1", "run-123", status="blocked"),
        _build_observation("observe-2", "run-123", status="blocked"),
        _build_observation("observe-3", "run-123", status="blocked"),
        _build_observation("observe-4", "run-123", status="blocked"),
    ]

    runtime = TaskGraphRuntime(
        observer_agent=ObserverAgent(observation_provider=lambda _session: observations.pop(0)),
        step_policy_agent=StepPolicyAgent(
            step_policy=lambda _session: _step_decision(StepDecisionType.OBSERVE_AGAIN, "again")
        ),
        verifier_agent=VerifierAgent(),
        recovery_agent=RecoveryAgent(),
    )

    session = runtime.create_session(
        "Manual dynamic max iterations plan",
        target_kind=EntityKind.RUN,
        target_id="run-123",
        verification_spec=_verification_spec(),
    )
    session.plan = TaskPlan(
        plan_id="plan-max",
        summary="Dynamic max iteration plan.",
        steps=[
            TaskStep(
                step_id="step-dynamic-max",
                kind=TaskStepKind.DYNAMIC,
                goal="Keep observing until max iterations.",
                verification_target_kind=EntityKind.RUN,
                verification_target_id="run-123",
                verification_spec=_verification_spec(),
                policy=TaskStepPolicy(
                    policy_id="policy-max",
                    description="Low max iteration policy.",
                    max_iterations=3,
                ),
            )
        ],
    )

    failed = runtime.run(session)

    assert failed.status == TaskStatus.FAILED
    assert failed.recovery_outcome is not None
    assert failed.last_verdict is not None
    assert failed.last_verdict.status == VerificationStatus.VERIFIED_FAILED


def test_task_graph_runtime_dynamic_step_executes_allowed_proposal() -> None:
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
        _build_observation("observe-2", "run-123", status="healthy"),
    ]

    def decide(session):
        if session.last_execution_result is None:
            return _step_decision(
                StepDecisionType.PROPOSE_EXECUTION,
                "execute",
                proposal=_proposal(),
            )
        return _step_decision(StepDecisionType.STEP_SUCCEEDED, "success")

    runtime = TaskGraphRuntime(
        observer_agent=ObserverAgent(observation_provider=lambda _session: observations.pop(0)),
        step_policy_agent=StepPolicyAgent(step_policy=decide),
        executor_agent=ExecutorAgent(adapter),
        verifier_agent=VerifierAgent(),
        recovery_agent=RecoveryAgent(),
    )

    completed = runtime.run(
        runtime.create_session(
            "[dynamic] Cancel the blocked run",
            target_kind=EntityKind.RUN,
            target_id="run-123",
            proposal=_proposal(),
            verification_spec=_verification_spec(),
        )
    )

    assert completed.status == TaskStatus.COMPLETED
    assert completed.pending_execution is None
    assert completed.last_execution_result is not None
    assert completed.last_execution_result.state == GovernedActionState.EXECUTED
    assert [result.role for result in completed.role_results] == [
        AgentRole.PLANNER,
        AgentRole.OBSERVER,
        AgentRole.STEP_POLICY,
        AgentRole.EXECUTOR,
        AgentRole.OBSERVER,
        AgentRole.STEP_POLICY,
        AgentRole.VERIFIER,
    ]


def test_task_graph_runtime_dynamic_step_rejects_disallowed_proposal() -> None:
    observations = [_build_observation("observe-1", "run-123", status="blocked")]
    disallowed = ExecutionProposal(
        proposal_id="proposal-2",
        action_tool_name="delete_run",
        arguments={"runId": "run-123"},
        target_kind=EntityKind.RUN,
        target_id="run-123",
        rationale="Delete the run.",
    )

    runtime = TaskGraphRuntime(
        observer_agent=ObserverAgent(observation_provider=lambda _session: observations.pop(0)),
        step_policy_agent=StepPolicyAgent(
            step_policy=lambda _session: _step_decision(
                StepDecisionType.PROPOSE_EXECUTION,
                "disallowed",
                proposal=disallowed,
            )
        ),
        executor_agent=ExecutorAgent(FakePlatformAdapter()),
        verifier_agent=VerifierAgent(),
        recovery_agent=RecoveryAgent(),
    )

    failed = runtime.run(
        runtime.create_session(
            "[dynamic] Cancel the blocked run",
            target_kind=EntityKind.RUN,
            target_id="run-123",
            proposal=_proposal(),
            verification_spec=_verification_spec(),
        )
    )

    assert failed.status == TaskStatus.FAILED
    assert failed.last_execution_result is None
    assert failed.recovery_outcome is not None


def test_task_graph_runtime_pauses_for_approval_and_resumes() -> None:
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
        _build_observation("observe-2", "run-123", status="healthy"),
    ]

    def observe(_session):
        return observations.pop(0)

    runtime = TaskGraphRuntime(
        observer_agent=ObserverAgent(observation_provider=observe),
        executor_agent=ExecutorAgent(adapter),
        verifier_agent=VerifierAgent(),
        recovery_agent=RecoveryAgent(),
    )
    paused = runtime.run(
        runtime.create_session(
            "Cancel the blocked run",
            target_kind=EntityKind.RUN,
            target_id="run-123",
            proposal=_proposal(),
            verification_spec=_verification_spec(),
        )
    )

    assert paused.status == TaskStatus.AWAITING_APPROVAL
    assert paused.pending_execution is not None
    assert paused.pending_execution.confirmation_id == "confirm-1"

    resumed = runtime.resume(paused, approved=True)

    assert resumed.status == TaskStatus.COMPLETED
    assert resumed.pending_execution is None
    assert resumed.last_verdict is not None
    assert resumed.last_verdict.status == VerificationStatus.VERIFIED_SUCCESS


def test_task_graph_runtime_dynamic_step_pauses_for_approval_and_resumes() -> None:
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
        _build_observation("observe-2", "run-123", status="healthy"),
    ]

    def decide(session):
        if session.last_execution_result is None:
            return _step_decision(
                StepDecisionType.PROPOSE_EXECUTION,
                "execute",
                proposal=_proposal(),
            )
        return _step_decision(StepDecisionType.STEP_SUCCEEDED, "success")

    runtime = TaskGraphRuntime(
        observer_agent=ObserverAgent(observation_provider=lambda _session: observations.pop(0)),
        step_policy_agent=StepPolicyAgent(step_policy=decide),
        executor_agent=ExecutorAgent(adapter),
        verifier_agent=VerifierAgent(),
        recovery_agent=RecoveryAgent(),
    )
    paused = runtime.run(
        runtime.create_session(
            "[dynamic] Cancel the blocked run",
            target_kind=EntityKind.RUN,
            target_id="run-123",
            proposal=_proposal(),
            verification_spec=_verification_spec(),
        )
    )

    assert paused.status == TaskStatus.AWAITING_APPROVAL
    assert paused.pending_execution is not None
    assert paused.pending_execution.proposal.action_tool_name == "cancel_run"

    resumed = runtime.resume(paused, approved=True)

    assert resumed.status == TaskStatus.COMPLETED
    assert resumed.pending_execution is None
    assert resumed.last_verdict is not None
    assert resumed.last_verdict.status == VerificationStatus.VERIFIED_SUCCESS


def test_task_graph_runtime_rejected_approval_routes_to_recovery() -> None:
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

    runtime = TaskGraphRuntime(
        observer_agent=ObserverAgent(observation_provider=observe),
        executor_agent=ExecutorAgent(adapter),
        verifier_agent=VerifierAgent(),
        recovery_agent=RecoveryAgent(recovery=recovery_outcome),
    )
    paused = runtime.run(
        runtime.create_session(
            "Cancel the blocked run",
            target_kind=EntityKind.RUN,
            target_id="run-123",
            proposal=_proposal(),
            verification_spec=_verification_spec(),
        )
    )
    failed = runtime.resume(paused, approved=False)

    assert failed.status == TaskStatus.FAILED
    assert failed.recovery_outcome is not None
    assert failed.last_verdict is not None
    assert failed.last_verdict.status == VerificationStatus.VERIFIED_FAILED
    assert [result.role for result in failed.role_results][-2:] == [AgentRole.RECOVERY, AgentRole.VERIFIER]


def test_task_graph_runtime_expired_approval_routes_to_recovery() -> None:
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
            summary="Recovery could not restore progress after approval expired.",
            target_kind=failure_verdict.target_kind,
            target_id=failure_verdict.target_id,
            evidence_refs=[
                EvidenceRef(
                    evidence_id=f"recovery-note:{session.session_id}",
                    kind=EvidenceKind.INLINE_NOTE,
                    summary="Approval expiry left the task unresolved.",
                    locator=session.session_id,
                )
            ],
        )

    runtime = TaskGraphRuntime(
        observer_agent=ObserverAgent(observation_provider=observe),
        executor_agent=ExecutorAgent(adapter),
        verifier_agent=VerifierAgent(),
        recovery_agent=RecoveryAgent(recovery=recovery_outcome),
    )
    paused = runtime.run(
        runtime.create_session(
            "Cancel the blocked run",
            target_kind=EntityKind.RUN,
            target_id="run-123",
            proposal=_proposal(),
            verification_spec=_verification_spec(),
        )
    )
    failed = runtime.resume(paused, expired=True)

    assert failed.status == TaskStatus.FAILED
    assert failed.recovery_outcome is not None
    assert failed.last_verdict is not None
    assert failed.last_verdict.status == VerificationStatus.VERIFIED_FAILED
    assert [result.role for result in failed.role_results][-2:] == [AgentRole.RECOVERY, AgentRole.VERIFIER]


def test_task_graph_runtime_dynamic_recovery_replan_retries_current_step() -> None:
    observations = [
        _build_observation("observe-1", "run-123", status="blocked"),
        _build_observation("observe-2", "run-123", status="healthy"),
    ]

    def decide(session):
        if not session.step_decisions:
            return _step_decision(
                StepDecisionType.STEP_BLOCKED,
                "blocked",
                blocked_reason="element_not_found",
            )
        return _step_decision(StepDecisionType.STEP_SUCCEEDED, "success")

    def recover(session, failure_verdict):
        return RecoveryOutcome(
            summary="Retry the current dynamic step after local replan.",
            target_kind=failure_verdict.target_kind,
            target_id=failure_verdict.target_id,
            replan_decision=ReplanDecision(
                decision_type=ReplanDecisionType.RETRY_CURRENT_STEP,
                summary="Retry current step.",
            ),
            evidence_refs=[
                EvidenceRef(
                    evidence_id=f"replan-note:{session.session_id}",
                    kind=EvidenceKind.INLINE_NOTE,
                    summary="Retry current step.",
                    locator=session.session_id,
                )
            ],
        )

    runtime = TaskGraphRuntime(
        observer_agent=ObserverAgent(observation_provider=lambda _session: observations.pop(0)),
        step_policy_agent=StepPolicyAgent(step_policy=decide),
        verifier_agent=VerifierAgent(),
        recovery_agent=RecoveryAgent(recovery=recover),
    )

    completed = runtime.run(
        runtime.create_session(
            "[dynamic] Inspect blocked task",
            target_kind=EntityKind.RUN,
            target_id="run-123",
            verification_spec=_verification_spec(),
        )
    )

    assert completed.status == TaskStatus.COMPLETED
    assert completed.current_step is not None
    assert completed.step_policy_iterations[completed.current_step.step_id] == 1
    assert [decision.decision_type for decision in completed.step_decisions] == [
        StepDecisionType.STEP_BLOCKED,
        StepDecisionType.STEP_SUCCEEDED,
    ]


def test_task_graph_runtime_dynamic_recovery_replan_skips_to_verification_step() -> None:
    runtime = TaskGraphRuntime(
        observer_agent=ObserverAgent(observation_provider=lambda _session: _build_observation("observe-1", "run-123")),
        step_policy_agent=StepPolicyAgent(
            step_policy=lambda _session: _step_decision(
                StepDecisionType.STEP_BLOCKED,
                "blocked",
                blocked_reason="already_satisfied_elsewhere",
            )
        ),
        verifier_agent=VerifierAgent(),
        recovery_agent=RecoveryAgent(
            recovery=lambda session, failure_verdict: RecoveryOutcome(
                summary="Skip to explicit verification step.",
                target_kind=failure_verdict.target_kind,
                target_id=failure_verdict.target_id,
                replan_decision=ReplanDecision(
                    decision_type=ReplanDecisionType.SKIP_CURRENT_STEP,
                    summary="Skip current step.",
                ),
                evidence_refs=[
                    EvidenceRef(
                        evidence_id=f"skip-note:{session.session_id}",
                        kind=EvidenceKind.INLINE_NOTE,
                        summary="Skip current step.",
                        locator=session.session_id,
                    )
                ],
            )
        ),
    )
    session = runtime.create_session(
        "Manual dynamic plan",
        target_kind=EntityKind.RUN,
        target_id="run-123",
        verification_spec=_verification_spec(),
    )
    session.contract = TaskContract(
        contract_id="contract-1",
        user_goal=session.goal,
        outcome="Verify run health.",
        target_kind=EntityKind.RUN,
        target_id="run-123",
        success_criteria=[
            SuccessCriterion(
                criterion_id="primary",
                description="The run is healthy.",
                evidence_hint="healthy",
            )
        ],
    )
    session.plan = TaskPlan(
        plan_id="plan-1",
        summary="Dynamic step followed by explicit verification.",
        steps=[
            TaskStep(
                step_id="step-dynamic",
                kind=TaskStepKind.DYNAMIC,
                goal="Reach verifiable state.",
                verification_target_kind=EntityKind.RUN,
                verification_target_id="run-123",
                policy=TaskStepPolicy(
                    policy_id="policy-1",
                    description="Try dynamic state preparation.",
                ),
            ),
            TaskStep(
                step_id="step-verify",
                kind=TaskStepKind.VERIFY,
                goal="Verify run health.",
                verification_target_kind=EntityKind.RUN,
                verification_target_id="run-123",
                verification_spec=_verification_spec(),
            ),
        ],
    )

    completed = runtime.run(session)

    assert completed.status == TaskStatus.COMPLETED
    assert completed.current_step is not None
    assert completed.current_step.step_id == "step-verify"
    assert completed.last_verdict is not None
    assert completed.last_verdict.status == VerificationStatus.VERIFIED_SUCCESS


def test_task_graph_runtime_dynamic_recovery_replan_handoff_and_fail() -> None:
    for decision_type, expected_status in [
        (ReplanDecisionType.HANDOFF, TaskStatus.HANDED_OFF),
        (ReplanDecisionType.FAIL, TaskStatus.FAILED),
    ]:
        observations = [_build_observation(f"observe-{decision_type.value}", "run-123", status="blocked")]
        runtime = TaskGraphRuntime(
            observer_agent=ObserverAgent(observation_provider=lambda _session: observations.pop(0)),
            step_policy_agent=StepPolicyAgent(
                step_policy=lambda _session: _step_decision(
                    StepDecisionType.REQUEST_REPLAN,
                    decision_type.value,
                    blocked_reason=decision_type.value,
                )
            ),
            verifier_agent=VerifierAgent(),
            recovery_agent=RecoveryAgent(
                recovery=lambda session, failure_verdict, decision_type=decision_type: RecoveryOutcome(
                    summary=f"Recovery requested {decision_type.value}.",
                    target_kind=failure_verdict.target_kind,
                    target_id=failure_verdict.target_id,
                    replan_decision=ReplanDecision(
                        decision_type=decision_type,
                        summary=f"Apply {decision_type.value}.",
                    ),
                    evidence_refs=[
                        EvidenceRef(
                            evidence_id=f"replan-note:{session.session_id}:{decision_type.value}",
                            kind=EvidenceKind.INLINE_NOTE,
                            summary=f"Apply {decision_type.value}.",
                            locator=session.session_id,
                        )
                    ],
                )
            ),
        )

        result = runtime.run(
            runtime.create_session(
                "[dynamic] Inspect blocked task",
                target_kind=EntityKind.RUN,
                target_id="run-123",
                verification_spec=_verification_spec(),
            )
        )

        assert result.status == expected_status


def test_task_graph_runtime_sqlite_checkpointer_persists_session_state(artifact_tmp_path) -> None:
    sqlite_path = str(artifact_tmp_path / "task-graph.sqlite3")
    config = RuntimeCheckpointConfig(
        mode=RuntimeCheckpointMode.SQLITE,
        sqlite_path=sqlite_path,
    )
    observations = [_build_observation("observe-1", "run-123", status="healthy")]

    def observe(_session):
        return observations.pop(0)

    runtime = TaskGraphRuntime(
        observer_agent=ObserverAgent(observation_provider=observe),
        verifier_agent=VerifierAgent(),
        recovery_agent=RecoveryAgent(),
        checkpointer=create_checkpointer(config),
    )

    completed = runtime.run(
        runtime.create_session(
            "Inspect blocked task",
            target_kind=EntityKind.RUN,
            target_id="run-123",
            verification_spec=_verification_spec(),
        )
    )
    graph_config = {"configurable": {"thread_id": completed.session_id}}
    persisted = TaskGraphState.model_validate(runtime._graph_app.get_state(graph_config).values).session

    runtime_b = TaskGraphRuntime(checkpointer=create_checkpointer(config))
    persisted_again = TaskGraphState.model_validate(runtime_b._graph_app.get_state(graph_config).values).session

    assert persisted.session_id == completed.session_id
    assert persisted.status == TaskStatus.COMPLETED
    assert persisted_again.session_id == completed.session_id
    assert persisted_again.status == TaskStatus.COMPLETED


def test_task_harness_service_can_use_task_graph_runtime_for_approval_flow() -> None:
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
        _build_observation("observe-2", "run-123", status="healthy"),
    ]

    def observe(_session):
        return observations.pop(0)

    harness = TaskHarnessService(
        orchestrator=TaskGraphRuntime(
            observer_agent=ObserverAgent(observation_provider=observe),
            executor_agent=ExecutorAgent(adapter),
            verifier_agent=VerifierAgent(),
            recovery_agent=RecoveryAgent(),
        ),
        store=InMemoryTaskHarnessStore(),
    )

    started = harness.start(
        TaskHarnessRequest(
            goal="Cancel the blocked run",
            target_kind=EntityKind.RUN,
            target_id="run-123",
            proposal=_proposal(),
            verification_spec=_verification_spec(),
        )
    )

    assert started.status == TaskHarnessStatus.AWAITING_APPROVAL
    resumed = harness.resume_approval(started.job_id, approved=True)

    assert resumed.status == TaskHarnessStatus.COMPLETED
    assert resumed.latest_verdict is not None
    assert resumed.latest_verdict.status == VerificationStatus.VERIFIED_SUCCESS
