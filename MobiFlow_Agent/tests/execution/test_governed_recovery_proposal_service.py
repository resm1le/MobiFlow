from __future__ import annotations

import pytest

from mobiflow_agent.execution.recovery.proposal import GovernedRecoveryProposalService
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
    ToolRiskLevel,
)
from mobiflow_agent.execution.recovery.materializer import RecoveryMaterializationStatus


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


def _governance(status: str = "FAILED") -> RunGovernanceSnapshot:
    return RunGovernanceSnapshot(
        run_id="run-1",
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


def _lineage(*, pool_id: str | None = "pool-1", device_id: str = "device-1") -> RunLineageSnapshot:
    latest_attempt = _attempt_context(device_id=device_id)
    run_target = _run_target_context(latest_attempt=latest_attempt, device_id=device_id)
    return RunLineageSnapshot(
        run_id="run-1",
        run=RunDetailContext(
            run=RunSummaryContext(
                run_id="run-1",
                name="Original Run",
                description="nightly retry",
                pool_id=pool_id,
                status="FAILED",
                final_state="FAILED",
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
                    queued=0,
                    running=0,
                    retry_pending=0,
                    succeeded=0,
                    failed=1,
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
        blockers=["terminal_failure"],
        current_governed_options=["create_run", "create_single_device_run", "cancel_run", "continue_observe"],
    )


def _submit_result(state: GovernedActionState) -> GovernedActionResult:
    return GovernedActionResult(
        state=state,
        proposal_id="proposal-submit",
        action_tool_name="create_run",
        audit=ToolAuditRef(audit_id="audit-1", risk_level=ToolRiskLevel.EXECUTION),
        entity_refs=PlatformEntityRefs(proposal_id="proposal-submit", run_id="run-1"),
        confirmation_id="confirm-1" if state == GovernedActionState.APPROVAL_REQUIRED else None,
        confirmation_summary="Approve recovery action" if state == GovernedActionState.APPROVAL_REQUIRED else None,
        confirmation_expires_at=1710000009999 if state == GovernedActionState.APPROVAL_REQUIRED else None,
        result={"accepted": True},
    )


def test_prepare_ready_cancel_run_proposal_uses_only_run_id() -> None:
    adapter = FakePlatformAdapter(
        tool_catalog=[_catalog_item("cancel_run", ["runId"])],
        run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context())},
        run_governance_snapshots={"run-1": _governance(status="BLOCKED")},
        run_lineage_snapshots={"run-1": _lineage()},
        generated_failure_triage=[_triage_record()],
        recovery_guidance={"run-1": _guidance(recommended_action="cancel_run")},
    )
    service = GovernedRecoveryProposalService(adapter)

    response = service.prepare("rt-1")

    assert response.materialization_status == RecoveryMaterializationStatus.READY
    assert response.proposal is not None
    assert response.proposal.action_tool_name == "cancel_run"
    assert response.proposal.arguments == {"runId": "run-1"}


def test_prepare_materializes_create_single_device_run_with_device_binding() -> None:
    adapter = FakePlatformAdapter(
        tool_catalog=[
            _catalog_item(
                "create_single_device_run",
                ["name", "deviceId", "taskType", "profilePackage", "taskPayload", "runConfig", "artifactPolicy"],
            )
        ],
        run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context(), device_id="device-9")},
        run_governance_snapshots={"run-1": _governance()},
        run_lineage_snapshots={"run-1": _lineage(pool_id=None, device_id="device-9")},
        generated_failure_triage=[_triage_record()],
        recovery_guidance={"run-1": _guidance(recommended_action="create_single_device_run")},
    )
    service = GovernedRecoveryProposalService(adapter)

    response = service.prepare("rt-1")

    assert response.materialization_status == RecoveryMaterializationStatus.READY
    assert response.materialized_action is not None
    assert response.materialized_action.arguments["deviceId"] == "device-9"
    assert response.proposal is not None
    assert response.proposal.arguments["profilePackage"] == "profiles.demo"


def test_prepare_materializes_create_run_from_run_snapshot() -> None:
    adapter = FakePlatformAdapter(
        tool_catalog=[
            _catalog_item(
                "create_run",
                ["name", "devicePoolId", "taskType", "profilePackage", "taskPayload", "runConfig", "artifactPolicy"],
            )
        ],
        run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context())},
        run_governance_snapshots={"run-1": _governance()},
        run_lineage_snapshots={"run-1": _lineage(pool_id="pool-9")},
        generated_failure_triage=[_triage_record()],
        recovery_guidance={"run-1": _guidance(recommended_action="create_run")},
    )
    service = GovernedRecoveryProposalService(adapter)

    response = service.prepare("rt-1")

    assert response.materialization_status == RecoveryMaterializationStatus.READY
    assert response.materialized_action is not None
    assert response.materialized_action.arguments["devicePoolId"] == "pool-9"
    assert response.proposal is not None
    assert response.proposal.arguments["taskPayload"] == {"entry": "home"}


def test_create_run_missing_required_inputs_returns_requires_input_and_submit_is_skipped() -> None:
    adapter = FakePlatformAdapter(
        tool_catalog=[
            _catalog_item(
                "create_run",
                ["name", "devicePoolId", "taskType", "profilePackage", "taskPayload", "runConfig", "artifactPolicy"],
            )
        ],
        run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context())},
        run_governance_snapshots={"run-1": _governance()},
        run_lineage_snapshots={"run-1": _lineage(pool_id=None)},
        generated_failure_triage=[_triage_record(), _triage_record()],
        recovery_guidance={"run-1": _guidance(recommended_action="create_run")},
    )
    service = GovernedRecoveryProposalService(adapter)

    prepared = service.prepare("rt-1")
    submitted = service.submit("rt-1")

    assert prepared.materialization_status == RecoveryMaterializationStatus.REQUIRES_INPUT
    assert prepared.missing_inputs == ["devicePoolId"]
    assert prepared.proposal is None
    assert submitted.submission is None
    assert adapter.submitted_proposals == []


def test_prepare_continue_observe_returns_observe_only() -> None:
    adapter = FakePlatformAdapter(
        tool_catalog=[],
        run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context())},
        run_governance_snapshots={"run-1": _governance(status="CANCELLING")},
        run_lineage_snapshots={"run-1": _lineage()},
        generated_failure_triage=[_triage_record()],
        recovery_guidance={
            "run-1": _guidance(
                recommended_action="continue_observe",
                allowed_actions=["continue_observe"],
                requires_approval=False,
            )
        },
    )
    service = GovernedRecoveryProposalService(adapter)

    response = service.prepare("rt-1")

    assert response.materialization_status == RecoveryMaterializationStatus.OBSERVE_ONLY
    assert response.proposal is None
    assert response.blocked_reason == "continue_observe"


def test_prepare_blocks_when_recommended_action_is_not_allowed() -> None:
    adapter = FakePlatformAdapter(
        tool_catalog=[_catalog_item("create_run", ["name"])],
        run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context())},
        run_governance_snapshots={"run-1": _governance()},
        run_lineage_snapshots={"run-1": _lineage()},
        generated_failure_triage=[_triage_record()],
        recovery_guidance={"run-1": _guidance(recommended_action="create_run", allowed_actions=["continue_observe"])},
    )
    service = GovernedRecoveryProposalService(adapter)

    response = service.prepare("rt-1")

    assert response.materialization_status == RecoveryMaterializationStatus.BLOCKED
    assert response.blocked_reason == "recommended_action_not_allowed"
    assert response.proposal is None


def test_submit_ready_proposal_returns_approval_required_without_resolve() -> None:
    adapter = FakePlatformAdapter(
        tool_catalog=[_catalog_item("cancel_run", ["runId"])],
        run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context())},
        run_governance_snapshots={"run-1": _governance(status="BLOCKED")},
        run_lineage_snapshots={"run-1": _lineage()},
        generated_failure_triage=[_triage_record()],
        recovery_guidance={"run-1": _guidance(recommended_action="cancel_run")},
        submit_results=[_submit_result(GovernedActionState.APPROVAL_REQUIRED)],
    )
    service = GovernedRecoveryProposalService(adapter)

    response = service.submit("rt-1")

    assert len(adapter.submitted_proposals) == 1
    assert response.submission is not None
    assert response.submission.state == GovernedActionState.APPROVAL_REQUIRED
    assert response.submission.confirmation_id == "confirm-1"


def test_submit_ready_proposal_returns_completed_result() -> None:
    adapter = FakePlatformAdapter(
        tool_catalog=[_catalog_item("create_run", ["name", "devicePoolId", "taskType", "profilePackage", "taskPayload", "runConfig", "artifactPolicy"])],
        run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context())},
        run_governance_snapshots={"run-1": _governance()},
        run_lineage_snapshots={"run-1": _lineage(pool_id="pool-1")},
        generated_failure_triage=[_triage_record()],
        recovery_guidance={"run-1": _guidance(recommended_action="create_run")},
        submit_results=[_submit_result(GovernedActionState.EXECUTED)],
    )
    service = GovernedRecoveryProposalService(adapter)

    response = service.submit("rt-1")

    assert response.submission is not None
    assert response.submission.state == GovernedActionState.EXECUTED
    assert response.submission.audit is not None


def test_prepare_raises_when_run_id_cannot_be_resolved() -> None:
    service = GovernedRecoveryProposalService(
        FakePlatformAdapter(
            run_targets={"rt-1": _run_target_context(latest_attempt=None, latest_attempt_id=None)},
        )
    )

    with pytest.raises(ValueError, match="Could not resolve run_id"):
        service.prepare("rt-1")


def test_prepare_propagates_platform_adapter_error() -> None:
    class BrokenTriageAdapter(FakePlatformAdapter):
        def generate_failure_triage(self, run_target_id: str) -> FailureTriageRecord:
            raise PlatformAdapterError("AI_FAILURE_TRIAGE_NOT_ALLOWED", "Failure triage is not allowed.")

    service = GovernedRecoveryProposalService(
        BrokenTriageAdapter(
            run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context())},
            run_governance_snapshots={"run-1": _governance()},
            run_lineage_snapshots={"run-1": _lineage()},
            recovery_guidance={"run-1": _guidance(recommended_action="cancel_run")},
        )
    )

    with pytest.raises(PlatformAdapterError, match="Failure triage is not allowed"):
        service.prepare("rt-1")


