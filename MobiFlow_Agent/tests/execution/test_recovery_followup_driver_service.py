from __future__ import annotations

import pytest

from mobiflow_agent.common.contracts import EntityKind, EvidenceKind, EvidenceRef, VerificationStatus, VerificationVerdict
from mobiflow_agent.execution.recovery.execution import GovernedRecoveryExecutionResponse
from mobiflow_agent.platform.adapter import FakePlatformAdapter, PlatformAdapterError
from mobiflow_agent.platform.types import (
    AttemptContext,
    RunAttemptCounts,
    RunCounts,
    RunDetailContext,
    RunGovernanceSnapshot,
    RunLineageSnapshot,
    RunSummaryContext,
    RunTargetContext,
)
from mobiflow_agent.execution.followup.driver import (
    RecoveryFollowupDriverDecision,
    RecoveryFollowupDriverJob,
    RecoveryFollowupDriverService,
)
from mobiflow_agent.runtime.state import AgentRuntimeState, RuntimeLifecycle


def _attempt_context(*, run_id: str = "run-1", device_id: str = "device-1") -> AttemptContext:
    return AttemptContext(
        attempt_id="attempt-1",
        task_id="task-1",
        device_id=device_id,
        run_id=run_id,
        status="FAILED",
        final_state="FAILED",
        failure_reason="ui_not_found",
    )


def _run_target_context(
    *,
    latest_attempt: AttemptContext | None,
    latest_attempt_id: str | None = "attempt-1",
    device_id: str = "device-1",
) -> RunTargetContext:
    return RunTargetContext(
        run_target_id="rt-1",
        device_id=device_id,
        status="FAILED",
        attempt_count=2,
        current_task_id="task-1",
        latest_attempt_id=latest_attempt_id,
        failure_reason="ui_not_found",
        latest_attempt=latest_attempt,
    )


def _governance(
    *,
    run_id: str = "run-created",
    status: str = "QUEUED",
    blockers: list[str] | None = None,
    attempts_total: int = 0,
    queued: int = 1,
    running: int = 0,
    succeeded: int = 0,
    failed: int = 0,
    cancelled: int = 0,
) -> RunGovernanceSnapshot:
    return RunGovernanceSnapshot(
        run_id=run_id,
        status=status,
        target_counts=RunCounts(
            total_targets=max(1, queued + running + succeeded + failed + cancelled),
            queued=queued,
            running=running,
            retry_pending=0,
            succeeded=succeeded,
            failed=failed,
            cancelled=cancelled,
        ),
        attempt_counts=RunAttemptCounts(total=attempts_total, running=running, failed=failed, succeeded=succeeded),
        latest_attempt_ids=["attempt-created-1"] if attempts_total > 0 else [],
        blockers=blockers or [],
        last_updated_at=1710000000100,
    )


def _target(
    run_target_id: str,
    *,
    device_id: str,
    status: str,
) -> RunTargetContext:
    return RunTargetContext(
        run_target_id=run_target_id,
        device_id=device_id,
        status=status,
        attempt_count=0,
        latest_attempt_id=None,
        latest_attempt=None,
    )


def _lineage(
    *,
    run_id: str = "run-created",
    pool_id: str | None = "pool-1",
    targets: list[RunTargetContext] | None = None,
) -> RunLineageSnapshot:
    return RunLineageSnapshot(
        run_id=run_id,
        run=RunDetailContext(
            run=RunSummaryContext(
                run_id=run_id,
                name="Created Run",
                description="recovery run",
                pool_id=pool_id,
                status="QUEUED",
                final_state=None,
                task_type="smoke",
                profile_package="profiles.demo",
                priority=5,
                labels=["recovery"],
                source="agent",
                created_by="tester",
                max_retries_per_device=1,
                queue_timeout_ms=60000,
                cancel_requested=False,
                created_at=1710000000000,
                updated_at=1710000000100,
                counts=RunCounts(
                    total_targets=max(1, len(targets or [])),
                    queued=1,
                    running=0,
                    retry_pending=0,
                    succeeded=0,
                    failed=0,
                    cancelled=0,
                ),
            ),
            task_payload={"entry": "home"},
            run_config={"env": "staging"},
            artifact_policy={"retainDays": 7},
            targets=targets or [],
        ),
        targets=targets or [],
        attempts=[],
        blockers=[],
        current_governed_options=["create_run", "create_single_device_run", "cancel_run", "continue_observe"],
    )


def _verdict(status: VerificationStatus, *, summary: str = "completed") -> VerificationVerdict:
    evidence = [
        EvidenceRef(
            evidence_id="snapshot:test:run:rt-1",
            kind=EvidenceKind.PLATFORM_SNAPSHOT,
            summary="test snapshot",
            locator="rt-1",
        )
    ]
    return VerificationVerdict(
        verdict_id=f"verdict:{status.value}",
        status=status,
        summary=summary,
        target_kind=EntityKind.RUN_TARGET,
        target_id="rt-1",
        evidence_refs=evidence if status in {VerificationStatus.VERIFIED_SUCCESS, VerificationStatus.VERIFIED_FAILED} else [],
        blocked_reason="blocked_by_policy" if status == VerificationStatus.BLOCKED else None,
    )


def _execution_response(
    *,
    action_name: str,
    created_run_id: str | None,
    followup_required: bool,
    lifecycle: RuntimeLifecycle = RuntimeLifecycle.COMPLETED,
    verdict_status: VerificationStatus = VerificationStatus.VERIFIED_SUCCESS,
) -> GovernedRecoveryExecutionResponse:
    verdict = _verdict(verdict_status, summary=f"{action_name} completed")
    return GovernedRecoveryExecutionResponse(
        thread_id="thread-1",
        run_target_id="rt-1",
        run_id="run-1",
        action_name=action_name,
        created_run_id=created_run_id,
        followup_required=followup_required,
        lifecycle=lifecycle,
        verdict=verdict,
        approval_request=None,
        runtime_state=AgentRuntimeState(
            session_id="session-1",
            lifecycle=lifecycle,
            latest_verdict=verdict,
        ),
    )


def test_start_from_execution_cancel_run_returns_no_followup_without_scheduling() -> None:
    class TrackingAdapter(FakePlatformAdapter):
        def __init__(self) -> None:
            super().__init__()
            self.read_calls = 0

        def get_run_target(self, run_target_id: str) -> RunTargetContext:
            self.read_calls += 1
            return super().get_run_target(run_target_id)

    adapter = TrackingAdapter()
    service = RecoveryFollowupDriverService(adapter)

    response = service.start_from_execution(
        _execution_response(
            action_name="cancel_run",
            created_run_id=None,
            followup_required=False,
        )
    )

    assert response.decision == RecoveryFollowupDriverDecision.NO_FOLLOWUP
    assert response.job is None
    assert response.assessment is None
    assert adapter.read_calls == 0


def test_start_from_execution_create_run_returns_schedule_next() -> None:
    service = RecoveryFollowupDriverService(
        FakePlatformAdapter(
            run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context())},
            run_governance_snapshots={"run-created": _governance(status="QUEUED", attempts_total=0, queued=1)},
            run_lineage_snapshots={"run-created": _lineage(targets=[_target("rt-created", device_id="device-1", status="QUEUED")])},
        )
    )

    response = service.start_from_execution(
        _execution_response(
            action_name="create_run",
            created_run_id="run-created",
            followup_required=True,
        ),
        max_polls=3,
        poll_interval_seconds=15,
    )

    assert response.decision == RecoveryFollowupDriverDecision.SCHEDULE_NEXT
    assert response.job is not None
    assert response.job.poll_count == 1
    assert response.job.max_polls == 3
    assert response.next_poll_after_seconds == 15


def test_start_from_execution_terminal_followup_returns_complete() -> None:
    service = RecoveryFollowupDriverService(
        FakePlatformAdapter(
            run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context())},
            run_governance_snapshots={"run-created": _governance(status="RUNNING", attempts_total=1, queued=0, running=1)},
            run_lineage_snapshots={"run-created": _lineage(targets=[_target("rt-created", device_id="device-1", status="RUNNING")])},
        )
    )

    response = service.start_from_execution(
        _execution_response(
            action_name="create_run",
            created_run_id="run-created",
            followup_required=True,
        )
    )

    assert response.decision == RecoveryFollowupDriverDecision.COMPLETE
    assert response.job is None
    assert response.assessment is not None
    assert response.assessment.verdict is not None
    assert response.assessment.verdict.status == VerificationStatus.VERIFIED_SUCCESS


def test_start_from_execution_handoff_candidate_returns_handoff_only() -> None:
    service = RecoveryFollowupDriverService(
        FakePlatformAdapter(
            run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context())},
            run_governance_snapshots={"run-created": _governance(status="BLOCKED", blockers=["device_unavailable"], queued=0)},
            run_lineage_snapshots={"run-created": _lineage(targets=[_target("rt-created", device_id="device-1", status="BLOCKED")])},
        )
    )

    response = service.start_from_execution(
        _execution_response(
            action_name="create_run",
            created_run_id="run-created",
            followup_required=True,
        )
    )

    assert response.decision == RecoveryFollowupDriverDecision.HANDOFF_ONLY
    assert response.job is None
    assert response.next_recovery_run_target_id == "rt-created"


def test_tick_pending_returns_schedule_next_with_incremented_job() -> None:
    service = RecoveryFollowupDriverService(
        FakePlatformAdapter(
            run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context())},
            run_governance_snapshots={
                "run-created": [
                    _governance(status="QUEUED", attempts_total=0, queued=1),
                    _governance(status="QUEUED", attempts_total=0, queued=1),
                ]
            },
            run_lineage_snapshots={
                "run-created": [
                    _lineage(targets=[_target("rt-created", device_id="device-1", status="QUEUED")]),
                    _lineage(targets=[_target("rt-created", device_id="device-1", status="QUEUED")]),
                ]
            },
        )
    )

    started = service.start_from_execution(
        _execution_response(
            action_name="create_run",
            created_run_id="run-created",
            followup_required=True,
        ),
        max_polls=3,
        poll_interval_seconds=12,
    )
    response = service.tick(started.job)

    assert response.decision == RecoveryFollowupDriverDecision.SCHEDULE_NEXT
    assert response.job is not None
    assert response.job.poll_count == 2
    assert response.job.created_run_id == "run-created"
    assert response.next_poll_after_seconds == 12


def test_tick_verified_failed_with_unique_handoff_returns_handoff_only() -> None:
    service = RecoveryFollowupDriverService(
        FakePlatformAdapter(
            run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context())},
            run_governance_snapshots={
                "run-created": [
                    _governance(status="QUEUED", attempts_total=0, queued=1),
                    _governance(status="FAILED", queued=0, failed=1),
                ]
            },
            run_lineage_snapshots={
                "run-created": [
                    _lineage(targets=[_target("rt-created", device_id="device-1", status="QUEUED")]),
                    _lineage(targets=[_target("rt-created", device_id="device-1", status="FAILED")]),
                ]
            },
        )
    )

    started = service.start_from_execution(
        _execution_response(
            action_name="create_run",
            created_run_id="run-created",
            followup_required=True,
        )
    )
    response = service.tick(started.job)

    assert response.decision == RecoveryFollowupDriverDecision.HANDOFF_ONLY
    assert response.job is None
    assert response.next_recovery_run_target_id == "rt-created"


def test_tick_verified_failed_without_stable_handoff_returns_complete() -> None:
    service = RecoveryFollowupDriverService(
        FakePlatformAdapter(
            run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context())},
            run_governance_snapshots={
                "run-created": [
                    _governance(status="QUEUED", attempts_total=0, queued=1),
                    _governance(status="FAILED", queued=0, failed=2),
                ]
            },
            run_lineage_snapshots={
                "run-created": [
                    _lineage(targets=[_target("rt-created-a", device_id="device-1", status="QUEUED")]),
                    _lineage(
                        targets=[
                            _target("rt-created-a", device_id="device-1", status="FAILED"),
                            _target("rt-created-b", device_id="device-2", status="FAILED"),
                        ]
                    ),
                ]
            },
        )
    )

    started = service.start_from_execution(
        _execution_response(
            action_name="create_run",
            created_run_id="run-created",
            followup_required=True,
        )
    )
    response = service.tick(started.job)

    assert response.decision == RecoveryFollowupDriverDecision.COMPLETE
    assert response.job is None
    assert response.next_recovery_run_target_id is None
    assert response.assessment is not None
    assert response.assessment.verdict is not None
    assert response.assessment.verdict.status == VerificationStatus.VERIFIED_FAILED


def test_start_from_execution_requires_created_run_id_when_followup_required() -> None:
    service = RecoveryFollowupDriverService(FakePlatformAdapter())

    with pytest.raises(ValueError, match="created_run_id"):
        service.start_from_execution(
            _execution_response(
                action_name="create_run",
                created_run_id=None,
                followup_required=True,
            )
        )


def test_start_from_execution_requires_completed_execution_response() -> None:
    service = RecoveryFollowupDriverService(FakePlatformAdapter())

    with pytest.raises(ValueError, match="completed execution response"):
        service.start_from_execution(
            _execution_response(
                action_name="create_run",
                created_run_id="run-created",
                followup_required=True,
                lifecycle=RuntimeLifecycle.BLOCKED,
                verdict_status=VerificationStatus.BLOCKED,
            )
        )


def test_tick_rejects_invalid_job_state() -> None:
    service = RecoveryFollowupDriverService(FakePlatformAdapter())
    job = RecoveryFollowupDriverJob.model_construct(
        run_target_id="rt-1",
        source_run_id="run-1",
        created_run_id="run-created",
        action_name="create_run",
        expected_device_id=None,
        poll_count=3,
        max_polls=2,
        poll_interval_seconds=30,
    )

    with pytest.raises(ValueError, match="poll_count"):
        service.tick(job)


def test_driver_service_propagates_platform_adapter_error() -> None:
    class BrokenAdapter(FakePlatformAdapter):
        def get_run_governance_snapshot(self, run_id: str) -> RunGovernanceSnapshot:
            raise PlatformAdapterError("TRANSPORT_ERROR", "governance read failed", retryable=True)

    service = RecoveryFollowupDriverService(
        BrokenAdapter(
            run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context())},
            run_lineage_snapshots={"run-created": _lineage(targets=[_target("rt-created", device_id="device-1", status="QUEUED")])},
        )
    )

    with pytest.raises(PlatformAdapterError, match="governance read failed"):
        service.start_from_execution(
            _execution_response(
                action_name="create_run",
                created_run_id="run-created",
                followup_required=True,
            )
        )



