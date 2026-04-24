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
from mobiflow_agent.execution.followup.scheduling import (
    RecoveryFollowupDecision,
    RecoveryFollowupSchedulingService,
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


def test_start_pending_returns_continue_polling_with_next_poll() -> None:
    service = RecoveryFollowupSchedulingService(
        FakePlatformAdapter(
            run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context())},
            run_governance_snapshots={"run-created": _governance(status="QUEUED", attempts_total=0, queued=1)},
            run_lineage_snapshots={"run-created": _lineage(targets=[_target("rt-created", device_id="device-1", status="QUEUED")])},
        )
    )

    response = service.start("rt-1", "run-created", max_polls=3, poll_interval_seconds=15)

    assert response.decision == RecoveryFollowupDecision.CONTINUE_POLLING
    assert response.next_poll_after_seconds == 15
    assert response.session.poll_count == 1
    assert response.session.action_name == "create_run"


def test_tick_verified_success_returns_stop() -> None:
    service = RecoveryFollowupSchedulingService(
        FakePlatformAdapter(
            run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context())},
            run_governance_snapshots={
                "run-created": [
                    _governance(status="QUEUED", attempts_total=0, queued=1),
                    _governance(status="RUNNING", attempts_total=1, queued=0, running=1),
                ]
            },
            run_lineage_snapshots={
                "run-created": [
                    _lineage(targets=[_target("rt-created", device_id="device-1", status="QUEUED")]),
                    _lineage(targets=[_target("rt-created", device_id="device-1", status="RUNNING")]),
                ]
            },
        )
    )

    started = service.start("rt-1", "run-created")
    response = service.tick(started.session)

    assert response.decision == RecoveryFollowupDecision.STOP
    assert response.assessment.verdict is not None
    assert response.assessment.verdict.status == VerificationStatus.VERIFIED_SUCCESS
    assert response.session.poll_count == 2


def test_tick_blocked_with_unique_handoff_returns_handoff_only() -> None:
    service = RecoveryFollowupSchedulingService(
        FakePlatformAdapter(
            run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context())},
            run_governance_snapshots={
                "run-created": [
                    _governance(status="QUEUED", attempts_total=0, queued=1),
                    _governance(status="BLOCKED", blockers=["device_unavailable"], queued=0),
                ]
            },
            run_lineage_snapshots={
                "run-created": [
                    _lineage(targets=[_target("rt-created", device_id="device-1", status="QUEUED")]),
                    _lineage(targets=[_target("rt-created", device_id="device-1", status="BLOCKED")]),
                ]
            },
        )
    )

    started = service.start("rt-1", "run-created")
    response = service.tick(started.session)

    assert response.decision == RecoveryFollowupDecision.HANDOFF_ONLY
    assert response.next_recovery_run_target_id == "rt-created"
    assert response.assessment.verdict is not None
    assert response.assessment.verdict.status == VerificationStatus.BLOCKED


def test_tick_verified_failed_with_unique_handoff_returns_handoff_only() -> None:
    service = RecoveryFollowupSchedulingService(
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

    started = service.start("rt-1", "run-created")
    response = service.tick(started.session)

    assert response.decision == RecoveryFollowupDecision.HANDOFF_ONLY
    assert response.next_recovery_run_target_id == "rt-created"
    assert response.assessment.verdict is not None
    assert response.assessment.verdict.status == VerificationStatus.VERIFIED_FAILED


def test_tick_verified_failed_without_unique_handoff_returns_stop() -> None:
    service = RecoveryFollowupSchedulingService(
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

    started = service.start("rt-1", "run-created")
    response = service.tick(started.session)

    assert response.decision == RecoveryFollowupDecision.STOP
    assert response.next_recovery_run_target_id is None
    assert response.assessment.verdict is not None
    assert response.assessment.verdict.status == VerificationStatus.VERIFIED_FAILED


def test_pending_that_reaches_max_polls_is_forced_to_verified_unknown_stop() -> None:
    service = RecoveryFollowupSchedulingService(
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

    started = service.start("rt-1", "run-created", max_polls=2, poll_interval_seconds=10)
    response = service.tick(started.session)

    assert response.decision == RecoveryFollowupDecision.STOP
    assert response.next_poll_after_seconds is None
    assert response.assessment.status.value == "completed"
    assert response.assessment.verdict is not None
    assert response.assessment.verdict.status == VerificationStatus.VERIFIED_UNKNOWN


def test_tick_preserves_session_fields_and_increments_poll_count() -> None:
    service = RecoveryFollowupSchedulingService(
        FakePlatformAdapter(
            run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context(device_id="device-9"), device_id="device-9")},
            run_governance_snapshots={
                "run-created": [
                    _governance(status="QUEUED", attempts_total=0, queued=1),
                    _governance(status="QUEUED", attempts_total=0, queued=1),
                ]
            },
            run_lineage_snapshots={
                "run-created": [
                    _lineage(pool_id=None, targets=[_target("rt-created", device_id="device-9", status="QUEUED")]),
                    _lineage(pool_id=None, targets=[_target("rt-created", device_id="device-9", status="QUEUED")]),
                ]
            },
        )
    )

    started = service.start("rt-1", "run-created", max_polls=3, poll_interval_seconds=12)
    response = service.tick(started.session)

    assert response.session.poll_count == 2
    assert response.session.run_target_id == "rt-1"
    assert response.session.created_run_id == "run-created"
    assert response.session.action_name == "create_single_device_run"
    assert response.session.expected_device_id == "device-9"


def test_start_create_single_device_run_preserves_action_name() -> None:
    service = RecoveryFollowupSchedulingService(
        FakePlatformAdapter(
            run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context(device_id="device-9"), device_id="device-9")},
            run_governance_snapshots={"run-created": _governance(status="QUEUED", attempts_total=0, queued=1)},
            run_lineage_snapshots={"run-created": _lineage(pool_id=None, targets=[_target("rt-created", device_id="device-9", status="QUEUED")])},
        )
    )

    response = service.start("rt-1", "run-created")

    assert response.session.action_name == "create_single_device_run"


def test_scheduling_service_does_not_prepare_or_submit_next_recovery() -> None:
    class TrackingAdapter(FakePlatformAdapter):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.prepare_or_submit_called = False

        def submit_execution_proposal(self, proposal, caller_context):
            self.prepare_or_submit_called = True
            return super().submit_execution_proposal(proposal, caller_context)

    adapter = TrackingAdapter(
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
    service = RecoveryFollowupSchedulingService(adapter)

    started = service.start("rt-1", "run-created")
    response = service.tick(started.session)

    assert response.decision == RecoveryFollowupDecision.HANDOFF_ONLY
    assert adapter.prepare_or_submit_called is False


def test_scheduling_service_propagates_platform_adapter_error() -> None:
    class BrokenAdapter(FakePlatformAdapter):
        def get_run_governance_snapshot(self, run_id: str) -> RunGovernanceSnapshot:
            raise PlatformAdapterError("TRANSPORT_ERROR", "governance read failed", retryable=True)

    service = RecoveryFollowupSchedulingService(
        BrokenAdapter(
            run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context())},
            run_lineage_snapshots={"run-created": _lineage(targets=[_target("rt-created", device_id="device-1", status="QUEUED")])},
        )
    )

    with pytest.raises(PlatformAdapterError, match="governance read failed"):
        service.start("rt-1", "run-created")


