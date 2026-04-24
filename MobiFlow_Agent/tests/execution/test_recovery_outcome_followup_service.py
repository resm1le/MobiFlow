from __future__ import annotations

import pytest

from mobiflow_agent.common.contracts import VerificationStatus
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
from mobiflow_agent.execution.followup.outcome import (
    RecoveryFollowupStatus,
    RecoveryOutcomeFollowupService,
)


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


def test_assess_create_run_pending_when_created_run_is_queue_like_without_progress() -> None:
    service = RecoveryOutcomeFollowupService(
        FakePlatformAdapter(
            run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context())},
            run_governance_snapshots={"run-created": _governance(status="QUEUED", attempts_total=0, queued=1)},
            run_lineage_snapshots={"run-created": _lineage(targets=[_target("rt-created", device_id="device-1", status="QUEUED")])},
        )
    )

    response = service.assess("rt-1", "run-created")

    assert response.status == RecoveryFollowupStatus.PENDING
    assert response.context.action_name == "create_run"
    assert response.verdict is None
    assert response.next_recovery_run_target_id is None


def test_assess_create_run_returns_verified_success_when_attempts_exist() -> None:
    service = RecoveryOutcomeFollowupService(
        FakePlatformAdapter(
            run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context())},
            run_governance_snapshots={"run-created": _governance(status="RUNNING", attempts_total=1, queued=0, running=1)},
            run_lineage_snapshots={"run-created": _lineage(targets=[_target("rt-created", device_id="device-1", status="RUNNING")])},
        )
    )

    response = service.assess("rt-1", "run-created")

    assert response.status == RecoveryFollowupStatus.COMPLETED
    assert response.verdict is not None
    assert response.verdict.status == VerificationStatus.VERIFIED_SUCCESS


def test_assess_create_run_returns_blocked_with_handoff_for_single_blocked_target() -> None:
    service = RecoveryOutcomeFollowupService(
        FakePlatformAdapter(
            run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context())},
            run_governance_snapshots={"run-created": _governance(status="BLOCKED", blockers=["device_unavailable"], queued=0)},
            run_lineage_snapshots={"run-created": _lineage(targets=[_target("rt-created", device_id="device-1", status="BLOCKED")])},
        )
    )

    response = service.assess("rt-1", "run-created")

    assert response.status == RecoveryFollowupStatus.COMPLETED
    assert response.verdict is not None
    assert response.verdict.status == VerificationStatus.BLOCKED
    assert response.next_recovery_run_target_id == "rt-created"


def test_assess_create_run_returns_verified_failed_for_terminal_created_run() -> None:
    service = RecoveryOutcomeFollowupService(
        FakePlatformAdapter(
            run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context())},
            run_governance_snapshots={"run-created": _governance(status="FAILED", queued=0, failed=1)},
            run_lineage_snapshots={"run-created": _lineage(targets=[_target("rt-created", device_id="device-1", status="FAILED")])},
        )
    )

    response = service.assess("rt-1", "run-created")

    assert response.status == RecoveryFollowupStatus.COMPLETED
    assert response.verdict is not None
    assert response.verdict.status == VerificationStatus.VERIFIED_FAILED
    assert response.next_recovery_run_target_id == "rt-created"


def test_assess_create_run_returns_verified_unknown_for_contradictory_progress_signals() -> None:
    service = RecoveryOutcomeFollowupService(
        FakePlatformAdapter(
            run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context())},
            run_governance_snapshots={"run-created": _governance(status="RUNNING", attempts_total=0, queued=0, running=0)},
            run_lineage_snapshots={"run-created": _lineage(targets=[_target("rt-created", device_id="device-1", status="QUEUED")])},
        )
    )

    response = service.assess("rt-1", "run-created")

    assert response.status == RecoveryFollowupStatus.COMPLETED
    assert response.verdict is not None
    assert response.verdict.status == VerificationStatus.VERIFIED_UNKNOWN


def test_assess_create_single_device_run_returns_verified_success_when_device_binding_matches() -> None:
    service = RecoveryOutcomeFollowupService(
        FakePlatformAdapter(
            run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context(device_id="device-9"), device_id="device-9")},
            run_governance_snapshots={"run-created": _governance(status="RUNNING", attempts_total=1, queued=0, running=1)},
            run_lineage_snapshots={"run-created": _lineage(pool_id=None, targets=[_target("rt-created", device_id="device-9", status="RUNNING")])},
        )
    )

    response = service.assess("rt-1", "run-created")

    assert response.context.action_name == "create_single_device_run"
    assert response.status == RecoveryFollowupStatus.COMPLETED
    assert response.verdict is not None
    assert response.verdict.status == VerificationStatus.VERIFIED_SUCCESS


def test_assess_create_single_device_run_returns_verified_failed_when_device_binding_is_wrong() -> None:
    service = RecoveryOutcomeFollowupService(
        FakePlatformAdapter(
            run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context(device_id="device-9"), device_id="device-9")},
            run_governance_snapshots={"run-created": _governance(status="RUNNING", attempts_total=1, queued=0, running=1)},
            run_lineage_snapshots={"run-created": _lineage(pool_id=None, targets=[_target("rt-created", device_id="device-2", status="FAILED")])},
        )
    )

    response = service.assess("rt-1", "run-created")

    assert response.status == RecoveryFollowupStatus.COMPLETED
    assert response.verdict is not None
    assert response.verdict.status == VerificationStatus.VERIFIED_FAILED
    assert response.next_recovery_run_target_id == "rt-created"


def test_assess_create_single_device_run_returns_verified_unknown_when_binding_cannot_be_proven() -> None:
    service = RecoveryOutcomeFollowupService(
        FakePlatformAdapter(
            run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context(device_id="device-9"), device_id="device-9")},
            run_governance_snapshots={"run-created": _governance(status="RUNNING", attempts_total=1, queued=0, running=1)},
            run_lineage_snapshots={"run-created": _lineage(pool_id=None, targets=[])},
        )
    )

    response = service.assess("rt-1", "run-created")

    assert response.status == RecoveryFollowupStatus.COMPLETED
    assert response.verdict is not None
    assert response.verdict.status == VerificationStatus.VERIFIED_UNKNOWN


def test_assess_returns_no_handoff_when_multiple_failed_targets_exist() -> None:
    service = RecoveryOutcomeFollowupService(
        FakePlatformAdapter(
            run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context())},
            run_governance_snapshots={"run-created": _governance(status="FAILED", queued=0, failed=2)},
            run_lineage_snapshots={
                "run-created": _lineage(
                    targets=[
                        _target("rt-created-a", device_id="device-1", status="FAILED"),
                        _target("rt-created-b", device_id="device-2", status="FAILED"),
                    ]
                )
            },
        )
    )

    response = service.assess("rt-1", "run-created")

    assert response.status == RecoveryFollowupStatus.COMPLETED
    assert response.next_recovery_run_target_id is None


def test_assess_resolves_source_run_id_via_attempt_fallback() -> None:
    service = RecoveryOutcomeFollowupService(
        FakePlatformAdapter(
            run_targets={"rt-1": _run_target_context(latest_attempt=None, latest_attempt_id="attempt-1")},
            attempts={"attempt-1": _attempt_context(run_id="run-1", device_id="device-1")},
            run_governance_snapshots={"run-created": _governance(status="QUEUED")},
            run_lineage_snapshots={"run-created": _lineage(targets=[_target("rt-created", device_id="device-1", status="QUEUED")])},
        )
    )

    response = service.assess("rt-1", "run-created")

    assert response.context.source_run_id == "run-1"


def test_assess_propagates_platform_adapter_error_when_snapshot_read_fails() -> None:
    class BrokenAdapter(FakePlatformAdapter):
        def get_run_governance_snapshot(self, run_id: str) -> RunGovernanceSnapshot:
            raise PlatformAdapterError("TRANSPORT_ERROR", "governance read failed", retryable=True)

    service = RecoveryOutcomeFollowupService(
        BrokenAdapter(
            run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context())},
            run_lineage_snapshots={"run-created": _lineage(targets=[_target("rt-created", device_id="device-1", status="QUEUED")])},
        )
    )

    with pytest.raises(PlatformAdapterError, match="governance read failed"):
        service.assess("rt-1", "run-created")


