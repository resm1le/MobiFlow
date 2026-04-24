import sqlite3
from pathlib import Path

import pytest

from mobiflow_agent.agents.contracts import RecoveryOutcome
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
from mobiflow_agent.control import TaskOrchestratorService
from mobiflow_agent.platform.adapter import FakePlatformAdapter
from mobiflow_agent.platform.types import GovernedActionResult, GovernedActionState
from mobiflow_agent.runtime import (
    InMemoryTaskHarnessStore,
    SqliteTaskHarnessStore,
    TaskHarnessJob,
    TaskHarnessJobPolicy,
    TaskHarnessRequest,
    TaskHarnessSerializationError,
    TaskHarnessService,
    TaskHarnessStatus,
    TaskHarnessStoreError,
    TaskHeartbeatRunner,
    TaskHarnessTransitionError,
)
from mobiflow_agent.task.completion import TaskCompletionVerdict
from tests.artifacts import sqlite_path


def _local_sqlite_path(artifact_tmp_path: Path, name: str) -> Path:
    return sqlite_path(artifact_tmp_path, name)


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


def test_task_harness_service_start_completes_task() -> None:
    observations = [_build_observation("observe-1", "run-123", status="healthy")]

    def observe(_session):
        return observations.pop(0)

    harness = TaskHarnessService(
        orchestrator=TaskOrchestratorService(
            observer_agent=ObserverAgent(observation_provider=observe),
            verifier_agent=VerifierAgent(),
            recovery_agent=RecoveryAgent(),
        ),
        store=InMemoryTaskHarnessStore(),
    )

    response = harness.start(
        TaskHarnessRequest(
            goal="Inspect blocked task",
            target_kind=EntityKind.RUN,
            target_id="run-123",
            verification_spec=_verification_spec(),
        )
    )

    assert response.status == TaskHarnessStatus.COMPLETED
    assert response.completion_verdict == TaskCompletionVerdict.TASK_COMPLETED
    assert response.latest_verdict is not None
    assert response.latest_verdict.status == VerificationStatus.VERIFIED_SUCCESS


def test_task_harness_service_resumes_approval_flow() -> None:
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
        orchestrator=TaskOrchestratorService(
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
    assert started.approval_request is not None
    resumed = harness.resume_approval(started.job_id, approved=True)

    assert resumed.status == TaskHarnessStatus.COMPLETED
    assert resumed.latest_verdict is not None
    assert resumed.latest_verdict.status == VerificationStatus.VERIFIED_SUCCESS


def test_task_harness_service_rejects_terminal_resume_and_tick() -> None:
    observations = [_build_observation("observe-1", "run-123", status="healthy")]

    def observe(_session):
        return observations.pop(0)

    harness = TaskHarnessService(
        orchestrator=TaskOrchestratorService(
            observer_agent=ObserverAgent(observation_provider=observe),
            verifier_agent=VerifierAgent(),
            recovery_agent=RecoveryAgent(),
        ),
        store=InMemoryTaskHarnessStore(),
    )
    response = harness.start(
        TaskHarnessRequest(
            goal="Inspect blocked task",
            target_kind=EntityKind.RUN,
            target_id="run-123",
            verification_spec=_verification_spec(),
        )
    )

    with pytest.raises(TaskHarnessTransitionError):
        harness.resume_approval(response.job_id, approved=True)
    with pytest.raises(TaskHarnessTransitionError):
        harness.tick(response.job_id, now_ms=1)


def test_task_heartbeat_runner_schedules_and_hands_off_after_limit() -> None:
    observations = [
        _build_observation("observe-1", "run-123", status="blocked"),
        _build_observation("observe-2", "run-123", status="blocked"),
    ]

    def observe(_session):
        return observations.pop(0)

    def recover(_session, failure_verdict):
        return RecoveryOutcome(
            summary="Recovery could not restore progress.",
            target_kind=failure_verdict.target_kind if failure_verdict is not None else EntityKind.RUN,
            target_id=failure_verdict.target_id if failure_verdict is not None else "run-123",
            evidence_refs=[
                EvidenceRef(
                    evidence_id="recovery-note:1",
                    kind=EvidenceKind.INLINE_NOTE,
                    summary="Recovery exhausted current options.",
                    locator="run-123",
                )
            ],
        )

    store = InMemoryTaskHarnessStore()
    harness = TaskHarnessService(
        orchestrator=TaskOrchestratorService(
            observer_agent=ObserverAgent(observation_provider=observe),
            verifier_agent=VerifierAgent(),
            recovery_agent=RecoveryAgent(recovery=recover),
        ),
        store=store,
    )

    started = harness.start(
        TaskHarnessRequest(
            goal="Inspect blocked task",
            target_kind=EntityKind.RUN,
            target_id="run-123",
            verification_spec=_verification_spec(),
            policy=TaskHarnessJobPolicy(
                wake_interval_seconds=1,
                max_heartbeat_ticks=1,
                continue_on_handoff=True,
            ),
        )
    )

    assert started.status == TaskHarnessStatus.SCHEDULED
    assert started.context_handoff is not None

    runner = TaskHeartbeatRunner(harness)
    responses = runner.run_once(now_ms=started.next_wakeup_at, limit=10)

    assert len(responses) == 1
    assert responses[0].status == TaskHarnessStatus.HANDED_OFF
    assert responses[0].context_handoff is not None


def test_task_heartbeat_runner_isolates_single_job_failure() -> None:
    attempts = {"run": 0}

    def observe(_session):
        return _build_observation("observe-healthy", "run-123", status="healthy")

    class FailingOnceOrchestrator(TaskOrchestratorService):
        def run(self, session):
            attempts["run"] += 1
            if attempts["run"] == 1:
                raise RuntimeError("platform observation failed")
            return super().run(session)

    orchestrator = FailingOnceOrchestrator(
        observer_agent=ObserverAgent(observation_provider=observe),
        verifier_agent=VerifierAgent(),
        recovery_agent=RecoveryAgent(),
    )
    store = InMemoryTaskHarnessStore()
    policy = TaskHarnessJobPolicy(wake_interval_seconds=1, max_heartbeat_ticks=3, continue_on_handoff=True)
    for index in range(2):
        session = orchestrator.create_session(
            "Inspect blocked task",
            target_kind=EntityKind.RUN,
            target_id="run-123",
            verification_spec=_verification_spec(),
        )
        store.save_job(
            TaskHarnessJob(
                job_id=f"harness-job:{index}",
                session=session,
                runtime_state=orchestrator.export_runtime_state(session),
                status=TaskHarnessStatus.SCHEDULED,
                next_wakeup_at=100,
                policy=policy,
                created_at_ms=1,
                updated_at_ms=1,
            )
        )

    harness = TaskHarnessService(orchestrator=orchestrator, store=store)
    responses = TaskHeartbeatRunner(harness).run_once(now_ms=100, limit=10)

    assert [response.status for response in responses] == [
        TaskHarnessStatus.FAILED,
        TaskHarnessStatus.COMPLETED,
    ]
    assert responses[0].error == "platform observation failed"
    assert harness.get_job("harness-job:0").failure_count == 1


def test_sqlite_task_harness_store_roundtrips_job(artifact_tmp_path: Path) -> None:
    observations = [_build_observation("observe-1", "run-123", status="healthy")]

    def observe(_session):
        return observations.pop(0)

    sqlite_path = _local_sqlite_path(artifact_tmp_path, "task-harness")
    with SqliteTaskHarnessStore(str(sqlite_path)) as store:
        harness = TaskHarnessService(
            orchestrator=TaskOrchestratorService(
                observer_agent=ObserverAgent(observation_provider=observe),
                verifier_agent=VerifierAgent(),
                recovery_agent=RecoveryAgent(),
            ),
            store=store,
        )
        response = harness.start(
            TaskHarnessRequest(
                goal="Inspect blocked task",
                target_kind=EntityKind.RUN,
                target_id="run-123",
                verification_spec=_verification_spec(),
            )
        )
        job = harness.get_job(response.job_id)

    assert job.job_id == response.job_id
    assert job.last_response is not None
    assert job.last_response.status == TaskHarnessStatus.COMPLETED

    with SqliteTaskHarnessStore(str(sqlite_path)) as restored_store:
        restored_job = restored_store.get_job(response.job_id)

    assert restored_job.job_id == response.job_id
    assert restored_job.last_response is not None
    assert restored_job.last_response.status == TaskHarnessStatus.COMPLETED


def test_sqlite_task_harness_store_rejects_use_after_close(artifact_tmp_path: Path) -> None:
    store = SqliteTaskHarnessStore(str(_local_sqlite_path(artifact_tmp_path, "closed")))
    store.close()

    with pytest.raises(TaskHarnessStoreError):
        store.list_due_jobs(now_ms=1)


def test_sqlite_task_harness_store_reports_corrupted_payload(artifact_tmp_path: Path) -> None:
    sqlite_path = _local_sqlite_path(artifact_tmp_path, "corrupted")
    with SqliteTaskHarnessStore(str(sqlite_path)) as store:
        pass
    connection = sqlite3.connect(sqlite_path)
    try:
        with connection:
            connection.execute(
                """
                INSERT INTO task_harness_jobs (
                    job_id,
                    schema_version,
                    status,
                    next_wakeup_at,
                    created_at_ms,
                    updated_at_ms,
                    failure_count,
                    payload
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "harness-job:corrupted",
                    1,
                    TaskHarnessStatus.SCHEDULED.value,
                    10,
                    1,
                    1,
                    0,
                    "{not-json",
                ),
            )
    finally:
        connection.close()

    with SqliteTaskHarnessStore(str(sqlite_path)) as store:
        with pytest.raises(TaskHarnessSerializationError):
            store.get_job("harness-job:corrupted")
