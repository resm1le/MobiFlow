from __future__ import annotations

from pathlib import Path

import pytest

from mobiflow_agent.common.contracts import VerificationStatus
from mobiflow_agent.execution.recovery.execution import GovernedRecoveryExecutionService
from mobiflow_agent.platform.adapter import FakePlatformAdapter, PlatformAdapterError
from mobiflow_agent.platform.types import (
    AttemptContext,
    FailureCategory,
    FailureTriageRecord,
    FailureTriageValidation,
    GovernedActionResult,
    GovernedActionState,
    PlatformEntityRefs,
    RecoveryGuidance,
    RetryRecommendation,
    RunAttemptCounts,
    RunCounts,
    RunDetailContext,
    RunGovernanceSnapshot,
    RunLineageSnapshot,
    RunSummaryContext,
    RunTargetContext,
    SuggestedNextAction,
    ToolAuditRef,
    ToolCatalogItem,
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


def _catalog_item(name: str, required: list[str], *, requires_approval: bool = True) -> ToolCatalogItem:
    return ToolCatalogItem(
        name=name,
        title=name,
        description=name,
        tool_kind="action",
        risk_level=ToolRiskLevel.EXECUTION,
        requires_approval=requires_approval,
        confirmation_mode="always" if requires_approval else "never",
        input_schema={"type": "object", "required": required},
        semantic_tags=["recovery"],
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


def _triage_record() -> FailureTriageRecord:
    return FailureTriageRecord(
        triage_result_id="triage-1",
        run_target_id="rt-1",
        failure_category=FailureCategory.UI_NOT_FOUND,
        probable_cause="Login button was not visible.",
        confidence=0.87,
        retry_recommendation=RetryRecommendation.INSPECT_PROFILE,
        suggested_next_action=SuggestedNextAction.INSPECT_ARTIFACTS,
        operator_review_hints=["Check the latest screenshot."],
        evidence=["artifact:shot-1"],
        validation=FailureTriageValidation(valid=True, errors=[], warnings=[]),
        model_meta={"provider": "test"},
        generated_at=1710000000000,
    )


def _guidance(
    *,
    recommended_action: str,
    allowed_actions: list[str] | None = None,
    requires_approval: bool = True,
) -> RecoveryGuidance:
    return RecoveryGuidance(
        entity_kind="run",
        entity_id="run-1",
        allowed_actions=allowed_actions or [recommended_action, "continue_observe"],
        recommended_action=recommended_action,
        requires_approval=requires_approval,
        required_inputs=["runId"],
        prerequisites=["runId"],
        stop_conditions=["confirmation_pending"],
        stop_conditions_summary="Stop when confirmation is pending.",
        why_not_others="Other options do not clear the current blocker.",
        explanation=f"The run should use {recommended_action}.",
        confidence=0.88,
    )


def _governance(*, run_id: str = "run-1", status: str = "FAILED") -> RunGovernanceSnapshot:
    return RunGovernanceSnapshot(
        run_id=run_id,
        status=status,
        target_counts=RunCounts(
            total_targets=1,
            queued=0,
            running=0,
            retry_pending=0,
            succeeded=0,
            failed=1,
            cancelled=0,
        ),
        attempt_counts=RunAttemptCounts(total=1, running=0, failed=1, succeeded=0),
        latest_attempt_ids=["attempt-1"],
        blockers=["terminal_failure"],
        last_updated_at=1710000000100,
    )


def _lineage(
    *,
    run_id: str = "run-1",
    pool_id: str | None = "pool-1",
    device_id: str = "device-1",
) -> RunLineageSnapshot:
    latest_attempt = _attempt_context(run_id=run_id, device_id=device_id)
    run_target = RunTargetContext(
        run_target_id="rt-created" if run_id != "run-1" else "rt-1",
        device_id=device_id,
        status="FAILED" if run_id == "run-1" else "QUEUED",
        attempt_count=1,
        latest_attempt_id=latest_attempt.attempt_id,
        latest_attempt=latest_attempt,
    )
    return RunLineageSnapshot(
        run_id=run_id,
        run=RunDetailContext(
            run=RunSummaryContext(
                run_id=run_id,
                name="Original Run" if run_id == "run-1" else "Created Run",
                description="nightly retry",
                pool_id=pool_id,
                status="FAILED" if run_id == "run-1" else "QUEUED",
                final_state="FAILED" if run_id == "run-1" else None,
                task_type="smoke",
                profile_package="profiles.demo",
                priority=5,
                labels=["nightly"],
                source="agent",
                created_by="tester",
                max_retries_per_device=1,
                queue_timeout_ms=60000,
                cancel_requested=False,
                created_at=1710000000000,
                updated_at=1710000000100,
                counts=RunCounts(
                    total_targets=1,
                    queued=1 if run_id != "run-1" else 0,
                    running=0,
                    retry_pending=0,
                    succeeded=0,
                    failed=1 if run_id == "run-1" else 0,
                    cancelled=0,
                ),
            ),
            task_payload={"entry": "home"},
            run_config={"env": "staging"},
            artifact_policy={"retainDays": 7},
            targets=[run_target],
        ),
        targets=[run_target],
        attempts=[latest_attempt],
        blockers=["terminal_failure"] if run_id == "run-1" else [],
        current_governed_options=["create_run", "create_single_device_run", "cancel_run", "continue_observe"],
    )


def _submit_result(
    *,
    action_tool_name: str,
    state: GovernedActionState,
    confirmation_id: str | None = None,
    result: dict | None = None,
    error: ToolExecutionError | None = None,
    entity_refs: PlatformEntityRefs | None = None,
) -> GovernedActionResult:
    return GovernedActionResult(
        state=state,
        proposal_id="proposal-1",
        action_tool_name=action_tool_name,
        audit=ToolAuditRef(audit_id="audit-1", risk_level=ToolRiskLevel.EXECUTION),
        entity_refs=entity_refs or PlatformEntityRefs(proposal_id="proposal-1", run_id="run-1"),
        confirmation_id=confirmation_id,
        confirmation_summary="Approve recovery action" if confirmation_id else None,
        confirmation_expires_at=1710000009999 if confirmation_id else None,
        result=result or {},
        error=error,
    )


def test_start_returns_awaiting_approval_with_approval_request() -> None:
    service = GovernedRecoveryExecutionService(
        FakePlatformAdapter(
            tool_catalog=[_catalog_item("cancel_run", ["runId"])],
            run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context())},
            run_governance_snapshots={"run-1": _governance(status="BLOCKED")},
            run_lineage_snapshots={"run-1": _lineage()},
            generated_failure_triage=[_triage_record()],
            recovery_guidance={"run-1": _guidance(recommended_action="cancel_run")},
            submit_results=[
                _submit_result(
                    action_tool_name="cancel_run",
                    state=GovernedActionState.APPROVAL_REQUIRED,
                    confirmation_id="confirm-1",
                )
            ],
        )
    )

    response = service.start("rt-1")

    assert response.thread_id.startswith("recover-run-target:rt-1:")
    assert response.lifecycle == RuntimeLifecycle.AWAITING_APPROVAL
    assert response.approval_request is not None
    assert response.approval_request.confirmation_id == "confirm-1"
    assert response.run_id == "run-1"


def test_resume_approved_cancel_run_returns_verified_success() -> None:
    service = GovernedRecoveryExecutionService(
        FakePlatformAdapter(
            tool_catalog=[_catalog_item("cancel_run", ["runId"])],
            run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context())},
            run_governance_snapshots={"run-1": [_governance(status="BLOCKED"), _governance(status="CANCELLED")]},
            run_lineage_snapshots={"run-1": _lineage()},
            generated_failure_triage=[_triage_record()],
            recovery_guidance={"run-1": _guidance(recommended_action="cancel_run")},
            submit_results=[
                _submit_result(
                    action_tool_name="cancel_run",
                    state=GovernedActionState.APPROVAL_REQUIRED,
                    confirmation_id="confirm-1",
                )
            ],
            resolve_results=[
                _submit_result(
                    action_tool_name="cancel_run",
                    state=GovernedActionState.EXECUTED,
                    result={"executedAction": {"runId": "run-1", "accepted": True, "status": "CANCELLED"}},
                )
            ],
        )
    )

    paused = service.start("rt-1")
    response = service.resume(paused.thread_id, approved=True)

    assert response.lifecycle == RuntimeLifecycle.COMPLETED
    assert response.action_name == "cancel_run"
    assert response.created_run_id is None
    assert response.followup_required is False
    assert response.verdict is not None
    assert response.verdict.status == VerificationStatus.VERIFIED_SUCCESS


def test_resume_rejected_returns_blocked() -> None:
    service = GovernedRecoveryExecutionService(
        FakePlatformAdapter(
            tool_catalog=[_catalog_item("cancel_run", ["runId"])],
            run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context())},
            run_governance_snapshots={"run-1": _governance(status="BLOCKED")},
            run_lineage_snapshots={"run-1": _lineage()},
            generated_failure_triage=[_triage_record()],
            recovery_guidance={"run-1": _guidance(recommended_action="cancel_run")},
            submit_results=[
                _submit_result(
                    action_tool_name="cancel_run",
                    state=GovernedActionState.APPROVAL_REQUIRED,
                    confirmation_id="confirm-1",
                )
            ],
            resolve_results=[
                _submit_result(
                    action_tool_name="cancel_run",
                    state=GovernedActionState.FAILED,
                    error=ToolExecutionError(code="CONFIRMATION_REJECTED", message="User rejected confirmation."),
                )
            ],
        )
    )

    paused = service.start("rt-1")
    response = service.resume(paused.thread_id, approved=False)

    assert response.lifecycle == RuntimeLifecycle.BLOCKED
    assert response.verdict is not None
    assert response.verdict.status == VerificationStatus.BLOCKED
    assert response.verdict.blocked_reason == "approval_rejected"


def test_resume_expired_returns_blocked() -> None:
    service = GovernedRecoveryExecutionService(
        FakePlatformAdapter(
            tool_catalog=[_catalog_item("cancel_run", ["runId"])],
            run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context())},
            run_governance_snapshots={"run-1": _governance(status="BLOCKED")},
            run_lineage_snapshots={"run-1": _lineage()},
            generated_failure_triage=[_triage_record()],
            recovery_guidance={"run-1": _guidance(recommended_action="cancel_run")},
            submit_results=[
                _submit_result(
                    action_tool_name="cancel_run",
                    state=GovernedActionState.APPROVAL_REQUIRED,
                    confirmation_id="confirm-1",
                )
            ],
        )
    )

    paused = service.start("rt-1")
    response = service.resume(paused.thread_id, expired=True)

    assert response.lifecycle == RuntimeLifecycle.BLOCKED
    assert response.verdict is not None
    assert response.verdict.status == VerificationStatus.BLOCKED
    assert response.verdict.blocked_reason == "approval_expired"


def test_resume_invalid_confirmation_returns_blocked() -> None:
    service = GovernedRecoveryExecutionService(
        FakePlatformAdapter(
            tool_catalog=[_catalog_item("cancel_run", ["runId"])],
            run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context())},
            run_governance_snapshots={"run-1": _governance(status="BLOCKED")},
            run_lineage_snapshots={"run-1": _lineage()},
            generated_failure_triage=[_triage_record()],
            recovery_guidance={"run-1": _guidance(recommended_action="cancel_run")},
            submit_results=[
                _submit_result(
                    action_tool_name="cancel_run",
                    state=GovernedActionState.APPROVAL_REQUIRED,
                    confirmation_id="confirm-1",
                )
            ],
            resolve_results=[
                _submit_result(
                    action_tool_name="cancel_run",
                    state=GovernedActionState.FAILED,
                    error=ToolExecutionError(code="TOOL_CONFIRMATION_INVALID", message="Confirmation token expired."),
                )
            ],
        )
    )

    paused = service.start("rt-1")
    response = service.resume(paused.thread_id, approved=True)

    assert response.lifecycle == RuntimeLifecycle.BLOCKED
    assert response.verdict is not None
    assert response.verdict.status == VerificationStatus.BLOCKED
    assert response.verdict.blocked_reason == "approval_invalid"


def test_start_create_run_returns_verified_success_when_created_run_is_readable() -> None:
    service = GovernedRecoveryExecutionService(
        FakePlatformAdapter(
            tool_catalog=[
                _catalog_item(
                    "create_run",
                    ["name", "devicePoolId", "taskType", "profilePackage", "taskPayload", "runConfig", "artifactPolicy"],
                )
            ],
            run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context())},
            run_governance_snapshots={
                "run-1": _governance(status="FAILED"),
                "run-created": _governance(run_id="run-created", status="QUEUED"),
            },
            run_lineage_snapshots={"run-1": _lineage(), "run-created": _lineage(run_id="run-created")},
            generated_failure_triage=[_triage_record()],
            recovery_guidance={"run-1": _guidance(recommended_action="create_run")},
            submit_results=[
                _submit_result(
                    action_tool_name="create_run",
                    state=GovernedActionState.EXECUTED,
                    result={"executedAction": {"run": {"runId": "run-created"}}},
                    entity_refs=PlatformEntityRefs(proposal_id="proposal-1"),
                )
            ],
        )
    )

    response = service.start("rt-1")

    assert response.lifecycle == RuntimeLifecycle.COMPLETED
    assert response.action_name == "create_run"
    assert response.created_run_id == "run-created"
    assert response.followup_required is True
    assert response.verdict is not None
    assert response.verdict.status == VerificationStatus.VERIFIED_SUCCESS


def test_start_create_run_without_created_run_id_returns_verified_unknown() -> None:
    service = GovernedRecoveryExecutionService(
        FakePlatformAdapter(
            tool_catalog=[
                _catalog_item(
                    "create_run",
                    ["name", "devicePoolId", "taskType", "profilePackage", "taskPayload", "runConfig", "artifactPolicy"],
                )
            ],
            run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context())},
            run_governance_snapshots={"run-1": _governance(status="FAILED")},
            run_lineage_snapshots={"run-1": _lineage()},
            generated_failure_triage=[_triage_record()],
            recovery_guidance={"run-1": _guidance(recommended_action="create_run")},
            submit_results=[
                _submit_result(
                    action_tool_name="create_run",
                    state=GovernedActionState.EXECUTED,
                    result={"executedAction": {"accepted": True}},
                    entity_refs=PlatformEntityRefs(proposal_id="proposal-1"),
                )
            ],
        )
    )

    response = service.start("rt-1")

    assert response.lifecycle == RuntimeLifecycle.COMPLETED
    assert response.action_name == "create_run"
    assert response.created_run_id is None
    assert response.followup_required is False
    assert response.verdict is not None
    assert response.verdict.status == VerificationStatus.VERIFIED_UNKNOWN


def test_start_create_single_device_run_returns_verified_success_when_device_binding_matches() -> None:
    service = GovernedRecoveryExecutionService(
        FakePlatformAdapter(
            tool_catalog=[
                _catalog_item(
                    "create_single_device_run",
                    ["name", "deviceId", "taskType", "profilePackage", "taskPayload", "runConfig", "artifactPolicy"],
                )
            ],
            run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context(device_id="device-9"), device_id="device-9")},
            run_governance_snapshots={
                "run-1": _governance(status="FAILED"),
                "run-created": _governance(run_id="run-created", status="QUEUED"),
            },
            run_lineage_snapshots={"run-1": _lineage(pool_id=None, device_id="device-9"), "run-created": _lineage(run_id="run-created", pool_id=None, device_id="device-9")},
            generated_failure_triage=[_triage_record()],
            recovery_guidance={"run-1": _guidance(recommended_action="create_single_device_run")},
            submit_results=[
                _submit_result(
                    action_tool_name="create_single_device_run",
                    state=GovernedActionState.EXECUTED,
                    result={"executedAction": {"run": {"runId": "run-created"}}},
                    entity_refs=PlatformEntityRefs(proposal_id="proposal-1"),
                )
            ],
        )
    )

    response = service.start("rt-1")

    assert response.lifecycle == RuntimeLifecycle.COMPLETED
    assert response.action_name == "create_single_device_run"
    assert response.created_run_id == "run-created"
    assert response.followup_required is True
    assert response.verdict is not None
    assert response.verdict.status == VerificationStatus.VERIFIED_SUCCESS


def test_start_create_single_device_run_without_binding_proof_returns_verified_unknown() -> None:
    service = GovernedRecoveryExecutionService(
        FakePlatformAdapter(
            tool_catalog=[
                _catalog_item(
                    "create_single_device_run",
                    ["name", "deviceId", "taskType", "profilePackage", "taskPayload", "runConfig", "artifactPolicy"],
                )
            ],
            run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context(device_id="device-9"), device_id="device-9")},
            run_governance_snapshots={
                "run-1": _governance(status="FAILED"),
                "run-created": _governance(run_id="run-created", status="QUEUED"),
            },
            run_lineage_snapshots={"run-1": _lineage(pool_id=None, device_id="device-9"), "run-created": _lineage(run_id="run-created", pool_id=None, device_id="device-2")},
            generated_failure_triage=[_triage_record()],
            recovery_guidance={"run-1": _guidance(recommended_action="create_single_device_run")},
            submit_results=[
                _submit_result(
                    action_tool_name="create_single_device_run",
                    state=GovernedActionState.EXECUTED,
                    result={"executedAction": {"run": {"runId": "run-created"}}},
                    entity_refs=PlatformEntityRefs(proposal_id="proposal-1"),
                )
            ],
        )
    )

    response = service.start("rt-1")

    assert response.lifecycle == RuntimeLifecycle.COMPLETED
    assert response.verdict is not None
    assert response.verdict.status == VerificationStatus.VERIFIED_UNKNOWN


def test_start_continue_observe_returns_blocked_without_submit() -> None:
    adapter = FakePlatformAdapter(
        tool_catalog=[],
        run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context())},
        run_governance_snapshots={"run-1": _governance(status="FAILED")},
        run_lineage_snapshots={"run-1": _lineage()},
        generated_failure_triage=[_triage_record()],
        recovery_guidance={"run-1": _guidance(recommended_action="continue_observe", allowed_actions=["continue_observe"], requires_approval=False)},
    )
    service = GovernedRecoveryExecutionService(adapter)

    response = service.start("rt-1")

    assert response.lifecycle == RuntimeLifecycle.BLOCKED
    assert response.verdict is not None
    assert response.verdict.status == VerificationStatus.BLOCKED
    assert response.verdict.blocked_reason == "continue_observe_only"
    assert adapter.submitted_proposals == []


def test_start_propagates_platform_adapter_error_when_submit_transport_fails() -> None:
    class BrokenSubmitAdapter(FakePlatformAdapter):
        def submit_execution_proposal(self, proposal, caller_context):
            raise PlatformAdapterError("TRANSPORT_ERROR", "submit failed", retryable=True)

    service = GovernedRecoveryExecutionService(
        BrokenSubmitAdapter(
            tool_catalog=[_catalog_item("cancel_run", ["runId"])],
            run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context())},
            run_governance_snapshots={"run-1": _governance(status="BLOCKED")},
            run_lineage_snapshots={"run-1": _lineage()},
            generated_failure_triage=[_triage_record()],
            recovery_guidance={"run-1": _guidance(recommended_action="cancel_run")},
        )
    )

    with pytest.raises(PlatformAdapterError, match="submit failed"):
        service.start("rt-1")


def test_resume_propagates_platform_adapter_error_when_resolve_transport_fails() -> None:
    class BrokenResolveAdapter(FakePlatformAdapter):
        def resolve_approval(self, confirmation_id, approved, caller_context):
            raise PlatformAdapterError("TRANSPORT_ERROR", "resolve failed", retryable=True)

    service = GovernedRecoveryExecutionService(
        BrokenResolveAdapter(
            tool_catalog=[_catalog_item("cancel_run", ["runId"])],
            run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context())},
            run_governance_snapshots={"run-1": _governance(status="BLOCKED")},
            run_lineage_snapshots={"run-1": _lineage()},
            generated_failure_triage=[_triage_record()],
            recovery_guidance={"run-1": _guidance(recommended_action="cancel_run")},
            submit_results=[
                _submit_result(
                    action_tool_name="cancel_run",
                    state=GovernedActionState.APPROVAL_REQUIRED,
                    confirmation_id="confirm-1",
                )
            ],
        )
    )

    paused = service.start("rt-1")
    with pytest.raises(PlatformAdapterError, match="resolve failed"):
        service.resume(paused.thread_id, approved=True)


def test_get_state_returns_paused_runtime_state_without_replanning() -> None:
    service = GovernedRecoveryExecutionService(
        FakePlatformAdapter(
            tool_catalog=[_catalog_item("cancel_run", ["runId"])],
            run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context())},
            run_governance_snapshots={"run-1": _governance(status="BLOCKED")},
            run_lineage_snapshots={"run-1": _lineage()},
            generated_failure_triage=[_triage_record()],
            recovery_guidance={"run-1": _guidance(recommended_action="cancel_run")},
            submit_results=[
                _submit_result(
                    action_tool_name="cancel_run",
                    state=GovernedActionState.APPROVAL_REQUIRED,
                    confirmation_id="confirm-1",
                )
            ],
        )
    )

    paused = service.start("rt-1")
    state = service.get_state(paused.thread_id)

    assert state.lifecycle == RuntimeLifecycle.AWAITING_APPROVAL
    assert state.pending_execution is not None
    assert state.pending_execution.confirmation_id == "confirm-1"


def test_sqlite_checkpointer_supports_cross_instance_resume_for_governed_recovery(artifact_tmp_path: Path) -> None:
    sqlite_path = str(_sqlite_test_path(artifact_tmp_path, "governed-recovery"))
    service_a = GovernedRecoveryExecutionService(
        FakePlatformAdapter(
            tool_catalog=[_catalog_item("cancel_run", ["runId"])],
            run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context())},
            run_governance_snapshots={"run-1": _governance(status="BLOCKED")},
            run_lineage_snapshots={"run-1": _lineage()},
            generated_failure_triage=[_triage_record()],
            recovery_guidance={"run-1": _guidance(recommended_action="cancel_run")},
            submit_results=[
                _submit_result(
                    action_tool_name="cancel_run",
                    state=GovernedActionState.APPROVAL_REQUIRED,
                    confirmation_id="confirm-1",
                )
            ],
        ),
        checkpointer=create_checkpointer(
            RuntimeCheckpointConfig(mode=RuntimeCheckpointMode.SQLITE, sqlite_path=sqlite_path)
        ),
    )
    paused = service_a.start("rt-1")

    service_b = GovernedRecoveryExecutionService(
        FakePlatformAdapter(
            tool_catalog=[_catalog_item("cancel_run", ["runId"])],
            run_governance_snapshots={"run-1": _governance(status="CANCELLED")},
            run_lineage_snapshots={"run-1": _lineage()},
            resolve_results=[
                _submit_result(
                    action_tool_name="cancel_run",
                    state=GovernedActionState.EXECUTED,
                    result={"executedAction": {"runId": "run-1", "accepted": True, "status": "CANCELLED"}},
                )
            ],
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
    assert persisted.recovery_execution is not None
    assert persisted.recovery_execution.action_name == "cancel_run"

    resumed = service_b.resume(paused.thread_id, approved=True)

    assert resumed.lifecycle == RuntimeLifecycle.COMPLETED
    assert resumed.verdict is not None
    assert resumed.verdict.status == VerificationStatus.VERIFIED_SUCCESS


def test_sqlite_checkpointer_roundtrips_recovery_runtime_state_after_completion(artifact_tmp_path: Path) -> None:
    sqlite_path = str(_sqlite_test_path(artifact_tmp_path, "governed-recovery-created"))
    checkpointer_a = create_checkpointer(
        RuntimeCheckpointConfig(mode=RuntimeCheckpointMode.SQLITE, sqlite_path=sqlite_path)
    )
    service_a = GovernedRecoveryExecutionService(
        FakePlatformAdapter(
            tool_catalog=[
                _catalog_item(
                    "create_run",
                    ["name", "devicePoolId", "taskType", "profilePackage", "taskPayload", "runConfig", "artifactPolicy"],
                )
            ],
            run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context())},
            run_governance_snapshots={
                "run-1": _governance(status="FAILED"),
                "run-created": _governance(run_id="run-created", status="QUEUED"),
            },
            run_lineage_snapshots={"run-1": _lineage(), "run-created": _lineage(run_id="run-created")},
            generated_failure_triage=[_triage_record()],
            recovery_guidance={"run-1": _guidance(recommended_action="create_run")},
            submit_results=[
                _submit_result(
                    action_tool_name="create_run",
                    state=GovernedActionState.EXECUTED,
                    result={"executedAction": {"run": {"runId": "run-created"}}},
                    entity_refs=PlatformEntityRefs(proposal_id="proposal-1"),
                )
            ],
        ),
        checkpointer=checkpointer_a,
    )
    completed = service_a.start("rt-1")

    service_b = GovernedRecoveryExecutionService(
        FakePlatformAdapter(),
        checkpointer=create_checkpointer(
            RuntimeCheckpointConfig(mode=RuntimeCheckpointMode.SQLITE, sqlite_path=sqlite_path)
        ),
    )
    persisted = service_b.get_state(completed.thread_id)

    assert persisted.lifecycle == RuntimeLifecycle.COMPLETED
    assert persisted.latest_verdict is not None
    assert persisted.latest_verdict.status == VerificationStatus.VERIFIED_SUCCESS
    assert persisted.recovery_execution is not None
    assert persisted.recovery_execution.action_name == "create_run"
    assert persisted.recovery_execution.created_run_id == "run-created"
    assert persisted.recovery_observation is not None
    assert persisted.recovery_observation.created_governance is not None
    assert persisted.recovery_observation.created_governance.run_id == "run-created"



