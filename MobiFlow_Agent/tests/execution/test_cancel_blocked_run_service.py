from __future__ import annotations

from pathlib import Path

import pytest

from mobiflow_agent.execution.recovery.blocked_run import CancelBlockedRunService
from mobiflow_agent.common.contracts import VerificationStatus
from mobiflow_agent.platform.evidence import build_run_observation_view
from mobiflow_agent.platform.adapter import FakePlatformAdapter
from mobiflow_agent.platform.types import (
    GovernedActionResult,
    GovernedActionState,
    PlatformEntityRefs,
    ToolAuditRef,
    ToolExecutionError,
    ToolRiskLevel,
)
from mobiflow_agent.runtime.checkpointing import (
    RuntimeCheckpointConfig,
    RuntimeCheckpointMode,
    create_checkpointer,
)
from mobiflow_agent.runtime.state import RuntimeLifecycle
from tests.artifacts import sqlite_path


def _sqlite_test_path(artifact_tmp_path: Path, name: str) -> Path:
    return sqlite_path(artifact_tmp_path, name)


def _tool_audit(audit_id: str) -> ToolAuditRef:
    return ToolAuditRef(audit_id=audit_id, risk_level=ToolRiskLevel.EXECUTION)


def _governed_result(
    *,
    state: GovernedActionState,
    proposal_id: str = "proposal-1",
    confirmation_id: str | None = None,
    confirmation_summary: str | None = None,
    error: ToolExecutionError | None = None,
    audit_id: str = "audit-1",
) -> GovernedActionResult:
    return GovernedActionResult(
        state=state,
        proposal_id=proposal_id,
        action_tool_name="cancel_run",
        audit=_tool_audit(audit_id),
        entity_refs=PlatformEntityRefs(proposal_id=proposal_id, run_id="run-1"),
        confirmation_id=confirmation_id,
        confirmation_summary=confirmation_summary,
        confirmation_expires_at=1710000000000 if confirmation_id else None,
        result={"status": "ok"} if state != GovernedActionState.FAILED else {},
        error=error,
    )


def _run_observation(
    *,
    status: str | None,
    allow_cancel: bool,
    include_diagnosis: bool = True,
):
    governance_result = {
        "runId": "run-1",
        "status": status,
        "blockers": [{"code": "executor_stalled"}] if status == "BLOCKED" else [],
        "latestAttemptIds": ["attempt-1"] if include_diagnosis else [],
        "lastUpdatedAt": 1710000000100,
    }
    lineage_result = {
        "runId": "run-1",
        "currentGovernedOptions": ["cancel_run"] if allow_cancel else [],
        "latestArtifacts": [],
    }
    diagnosis_response = (
        {
            "status": "completed",
            "result": {
                "attemptId": "attempt-1",
                "keyEvents": [{"eventType": "STALL", "message": "Executor stalled"}],
                "failureSignals": [{"code": "stalled"}],
            },
        }
        if include_diagnosis
        else None
    )
    return build_run_observation_view(
        run_id="run-1",
        governance_response={"status": "completed", "result": governance_result},
        lineage_response={"status": "completed", "result": lineage_result},
        diagnosis_response=diagnosis_response,
    )


def test_start_returns_awaiting_approval_with_approval_request() -> None:
    service = CancelBlockedRunService(
        FakePlatformAdapter(
            run_observations={"run-1": [_run_observation(status="BLOCKED", allow_cancel=True)]},
            submit_results=[
                _governed_result(
                    state=GovernedActionState.APPROVAL_REQUIRED,
                    confirmation_id="confirm-1",
                    confirmation_summary="Approve cancelling run-1",
                )
            ],
        )
    )

    response = service.start("run-1")

    assert response.thread_id.startswith("cancel-run:run-1:")
    assert response.lifecycle == RuntimeLifecycle.AWAITING_APPROVAL
    assert response.verdict is None
    assert response.approval_request is not None
    assert response.approval_request.thread_id == response.thread_id
    assert response.approval_request.confirmation_id == "confirm-1"


def test_resume_approved_returns_verified_success() -> None:
    service = CancelBlockedRunService(
        FakePlatformAdapter(
            run_observations={
                "run-1": [
                    _run_observation(status="BLOCKED", allow_cancel=True),
                    _run_observation(status="CANCELLED", allow_cancel=False, include_diagnosis=False),
                ]
            },
            submit_results=[
                _governed_result(
                    state=GovernedActionState.APPROVAL_REQUIRED,
                    confirmation_id="confirm-1",
                    confirmation_summary="Approve cancelling run-1",
                )
            ],
            resolve_results=[_governed_result(state=GovernedActionState.EXECUTED, audit_id="audit-2")],
        )
    )

    paused = service.start("run-1")
    response = service.resume(paused.thread_id, approved=True)

    assert response.lifecycle == RuntimeLifecycle.COMPLETED
    assert response.verdict is not None
    assert response.verdict.status == VerificationStatus.VERIFIED_SUCCESS


def test_resume_rejected_returns_blocked() -> None:
    service = CancelBlockedRunService(
        FakePlatformAdapter(
            run_observations={"run-1": [_run_observation(status="BLOCKED", allow_cancel=True)]},
            submit_results=[
                _governed_result(
                    state=GovernedActionState.APPROVAL_REQUIRED,
                    confirmation_id="confirm-1",
                    confirmation_summary="Approve cancelling run-1",
                )
            ],
            resolve_results=[
                _governed_result(
                    state=GovernedActionState.FAILED,
                    audit_id="audit-2",
                    error=ToolExecutionError(code="CONFIRMATION_REJECTED", message="User rejected confirmation."),
                )
            ],
        )
    )

    paused = service.start("run-1")
    response = service.resume(paused.thread_id, approved=False)

    assert response.lifecycle == RuntimeLifecycle.BLOCKED
    assert response.verdict is not None
    assert response.verdict.status == VerificationStatus.BLOCKED
    assert response.verdict.blocked_reason == "approval_rejected"


def test_resume_expired_returns_blocked() -> None:
    service = CancelBlockedRunService(
        FakePlatformAdapter(
            run_observations={"run-1": [_run_observation(status="BLOCKED", allow_cancel=True)]},
            submit_results=[
                _governed_result(
                    state=GovernedActionState.APPROVAL_REQUIRED,
                    confirmation_id="confirm-1",
                    confirmation_summary="Approve cancelling run-1",
                )
            ],
        )
    )

    paused = service.start("run-1")
    response = service.resume(paused.thread_id, expired=True)

    assert response.lifecycle == RuntimeLifecycle.BLOCKED
    assert response.verdict is not None
    assert response.verdict.status == VerificationStatus.BLOCKED
    assert response.verdict.blocked_reason == "approval_expired"


def test_start_returns_verified_failed_when_submit_fails() -> None:
    service = CancelBlockedRunService(
        FakePlatformAdapter(
            run_observations={"run-1": [_run_observation(status="BLOCKED", allow_cancel=True)]},
            submit_results=[
                _governed_result(
                    state=GovernedActionState.FAILED,
                    error=ToolExecutionError(code="PLATFORM_ERROR", message="Execution failed."),
                )
            ],
        )
    )

    response = service.start("run-1")

    assert response.lifecycle == RuntimeLifecycle.COMPLETED
    assert response.verdict is not None
    assert response.verdict.status == VerificationStatus.VERIFIED_FAILED


def test_resume_invalid_confirmation_returns_blocked() -> None:
    service = CancelBlockedRunService(
        FakePlatformAdapter(
            run_observations={"run-1": [_run_observation(status="BLOCKED", allow_cancel=True)]},
            submit_results=[
                _governed_result(
                    state=GovernedActionState.APPROVAL_REQUIRED,
                    confirmation_id="confirm-1",
                    confirmation_summary="Approve cancelling run-1",
                )
            ],
            resolve_results=[
                _governed_result(
                    state=GovernedActionState.FAILED,
                    audit_id="audit-2",
                    error=ToolExecutionError(
                        code="TOOL_CONFIRMATION_INVALID",
                        message="Confirmation token expired.",
                    ),
                )
            ],
        )
    )

    paused = service.start("run-1")
    response = service.resume(paused.thread_id, approved=True)

    assert response.lifecycle == RuntimeLifecycle.BLOCKED
    assert response.verdict is not None
    assert response.verdict.status == VerificationStatus.BLOCKED
    assert response.verdict.blocked_reason == "approval_invalid"


def test_resume_raises_for_unknown_thread() -> None:
    service = CancelBlockedRunService(FakePlatformAdapter())

    with pytest.raises(ValueError, match="was not found"):
        service.resume("missing-thread", approved=True)


def test_resume_raises_when_state_is_not_awaiting_approval() -> None:
    service = CancelBlockedRunService(
        FakePlatformAdapter(
            run_observations={
                "run-1": [
                    _run_observation(status="BLOCKED", allow_cancel=True),
                    _run_observation(status="FAILED", allow_cancel=False, include_diagnosis=False),
                ]
            },
            submit_results=[_governed_result(state=GovernedActionState.EXECUTED)],
        )
    )

    completed = service.start("run-1")

    with pytest.raises(ValueError, match="is not awaiting approval"):
        service.resume(completed.thread_id, approved=True)


def test_resume_raises_when_no_decision_is_provided() -> None:
    service = CancelBlockedRunService(
        FakePlatformAdapter(
            run_observations={"run-1": [_run_observation(status="BLOCKED", allow_cancel=True)]},
            submit_results=[
                _governed_result(
                    state=GovernedActionState.APPROVAL_REQUIRED,
                    confirmation_id="confirm-1",
                    confirmation_summary="Approve cancelling run-1",
                )
            ],
        )
    )

    paused = service.start("run-1")

    with pytest.raises(ValueError, match="requires approved=True/False or expired=True"):
        service.resume(paused.thread_id)


def test_resume_raises_when_pending_execution_is_missing() -> None:
    service = CancelBlockedRunService(FakePlatformAdapter())

    class BrokenState:
        lifecycle = RuntimeLifecycle.AWAITING_APPROVAL
        pending_execution = None

    service.get_state = lambda thread_id: BrokenState()  # type: ignore[method-assign]

    with pytest.raises(ValueError, match="has no pending execution"):
        service.resume("broken-thread", approved=True)


def test_get_state_returns_paused_runtime_state_without_resuming() -> None:
    service = CancelBlockedRunService(
        FakePlatformAdapter(
            run_observations={"run-1": [_run_observation(status="BLOCKED", allow_cancel=True)]},
            submit_results=[
                _governed_result(
                    state=GovernedActionState.APPROVAL_REQUIRED,
                    confirmation_id="confirm-1",
                    confirmation_summary="Approve cancelling run-1",
                )
            ],
        )
    )

    paused = service.start("run-1")
    state = service.get_state(paused.thread_id)

    assert state.lifecycle == RuntimeLifecycle.AWAITING_APPROVAL
    assert state.pending_execution is not None
    assert state.pending_execution.confirmation_id == "confirm-1"


def test_sqlite_checkpointer_supports_cross_instance_resume_and_get_state(artifact_tmp_path: Path) -> None:
    sqlite_path = str(_sqlite_test_path(artifact_tmp_path, "cancel-checkpoint"))
    service_a = CancelBlockedRunService(
        FakePlatformAdapter(
            run_observations={"run-1": [_run_observation(status="BLOCKED", allow_cancel=True)]},
            submit_results=[
                _governed_result(
                    state=GovernedActionState.APPROVAL_REQUIRED,
                    confirmation_id="confirm-1",
                    confirmation_summary="Approve cancelling run-1",
                )
            ],
        ),
        checkpointer=create_checkpointer(
            RuntimeCheckpointConfig(mode=RuntimeCheckpointMode.SQLITE, sqlite_path=sqlite_path)
        ),
    )
    paused = service_a.start("run-1")

    service_b = CancelBlockedRunService(
        FakePlatformAdapter(
            run_observations={"run-1": [_run_observation(status="CANCELLED", allow_cancel=False, include_diagnosis=False)]},
            resolve_results=[_governed_result(state=GovernedActionState.EXECUTED, audit_id="audit-2")],
        ),
        checkpointer=create_checkpointer(
            RuntimeCheckpointConfig(mode=RuntimeCheckpointMode.SQLITE, sqlite_path=sqlite_path)
        ),
    )

    persisted = service_b.get_state(paused.thread_id)
    assert persisted.lifecycle == RuntimeLifecycle.AWAITING_APPROVAL
    assert persisted.pending_execution is not None
    assert persisted.pending_execution.confirmation_id == "confirm-1"
    assert persisted.pending_execution.audit is not None
    assert persisted.pending_execution.audit.audit_id == "audit-1"
    assert persisted.pending_execution.entity_refs is not None
    assert persisted.pending_execution.entity_refs.run_id == "run-1"

    resumed = service_b.resume(paused.thread_id, approved=True)

    assert resumed.lifecycle == RuntimeLifecycle.COMPLETED
    assert resumed.verdict is not None
    assert resumed.verdict.status == VerificationStatus.VERIFIED_SUCCESS



