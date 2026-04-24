from __future__ import annotations

from uuid import uuid4

from mobiflow_agent.common.contracts import (
    EntityKind,
    VerificationCheck,
    VerificationSpec,
    VerificationStatus,
    VerificationVerdict,
)
from mobiflow_agent.execution.recovery.governed.evidence import (
    EMPTY_GOVERNED_RECOVERY_EVIDENCE,
    result_evidence_from_state,
    snapshot_evidence,
)
from mobiflow_agent.execution.recovery.materializer import RecoveryMaterializationStatus
from mobiflow_agent.runtime.state import AgentRuntimeState, RecoveryExecutionContext, RecoveryObservationResult


def build_recovery_verification_spec(recovery_execution: RecoveryExecutionContext) -> VerificationSpec:
    if recovery_execution.action_name == "cancel_run":
        checks = [
            VerificationCheck(
                check_id="source_run_cancelled",
                description="Source run status is CANCELLED in the latest governance snapshot.",
                evidence_hint="get_run_governance_snapshot",
            )
        ]
    elif recovery_execution.action_name == "create_single_device_run":
        checks = [
            VerificationCheck(
                check_id="created_run_exists",
                description="A replacement run exists and can be read from governance snapshot.",
                evidence_hint="get_run_governance_snapshot",
            ),
            VerificationCheck(
                check_id="device_binding_preserved",
                description="The replacement run lineage includes the expected device binding.",
                evidence_hint="get_run_lineage_snapshot",
            ),
        ]
    else:
        checks = [
            VerificationCheck(
                check_id="created_run_exists",
                description="A replacement run exists and can be read from governance snapshot.",
                evidence_hint="get_run_governance_snapshot",
            )
        ]
    return VerificationSpec(
        verification_id=f"verification:{recovery_execution.proposal_id}",
        target_kind=EntityKind.RUN_TARGET,
        target_id=recovery_execution.run_target_id,
        success_checks=checks,
        blocked_conditions=["approval_rejected", "approval_expired", "approval_invalid", "continue_observe_only"],
    )


def prepare_blocked_reason(
    status: RecoveryMaterializationStatus,
    blocked_reason: str | None,
) -> str:
    if status == RecoveryMaterializationStatus.OBSERVE_ONLY:
        return "continue_observe_only"
    if status == RecoveryMaterializationStatus.REQUIRES_INPUT:
        return blocked_reason or "missing_materialization_inputs"
    return blocked_reason or "recovery_prepare_blocked"


def verify_recovery(
    state: AgentRuntimeState,
    recovery_execution: RecoveryExecutionContext,
    observation: RecoveryObservationResult | None,
) -> VerificationVerdict:
    if recovery_execution.action_name == "cancel_run":
        return verify_cancel_recovery(state, recovery_execution, observation)
    if recovery_execution.action_name == "create_run":
        return verify_create_run_recovery(state, recovery_execution, observation)
    if recovery_execution.action_name == "create_single_device_run":
        return verify_single_device_recovery(state, recovery_execution, observation)
    return VerificationVerdict(
        verdict_id=f"verdict:{uuid4().hex}",
        status=VerificationStatus.BLOCKED,
        summary=f"Recovery action {recovery_execution.action_name} is not executable in the current recovery closure.",
        target_kind=EntityKind.RUN_TARGET,
        target_id=recovery_execution.run_target_id,
        blocked_reason="unsupported_recovery_action",
        evidence_refs=result_evidence_from_state(
            state,
            empty_summary_template=EMPTY_GOVERNED_RECOVERY_EVIDENCE,
        ),
    )


def verify_cancel_recovery(
    state: AgentRuntimeState,
    recovery_execution: RecoveryExecutionContext,
    observation: RecoveryObservationResult | None,
) -> VerificationVerdict:
    source_governance = observation.source_governance if observation else None
    if source_governance is not None and source_governance.status == "CANCELLED":
        return VerificationVerdict(
            verdict_id=f"verdict:{uuid4().hex}",
            status=VerificationStatus.VERIFIED_SUCCESS,
            summary=f"Run {recovery_execution.source_run_id} is CANCELLED in the latest governance snapshot.",
            target_kind=EntityKind.RUN,
            target_id=recovery_execution.source_run_id,
            matched_check_ids=["source_run_cancelled"],
            evidence_refs=snapshot_evidence("get_run_governance_snapshot", recovery_execution.source_run_id),
        )
    if source_governance is not None and source_governance.status:
        return VerificationVerdict(
            verdict_id=f"verdict:{uuid4().hex}",
            status=VerificationStatus.VERIFIED_FAILED,
            summary=f"Run {recovery_execution.source_run_id} is still {source_governance.status} after the governed recovery action.",
            target_kind=EntityKind.RUN,
            target_id=recovery_execution.source_run_id,
            unmatched_check_ids=["source_run_cancelled"],
            evidence_refs=snapshot_evidence("get_run_governance_snapshot", recovery_execution.source_run_id),
        )
    return VerificationVerdict(
        verdict_id=f"verdict:{uuid4().hex}",
        status=VerificationStatus.VERIFIED_UNKNOWN,
        summary=(
            f"Recovery action completed but the latest observation could not prove whether run "
            f"{recovery_execution.source_run_id} was cancelled."
        ),
        target_kind=EntityKind.RUN,
        target_id=recovery_execution.source_run_id,
        evidence_refs=result_evidence_from_state(
            state,
            empty_summary_template=EMPTY_GOVERNED_RECOVERY_EVIDENCE,
        ),
    )


def verify_create_run_recovery(
    state: AgentRuntimeState,
    recovery_execution: RecoveryExecutionContext,
    observation: RecoveryObservationResult | None,
) -> VerificationVerdict:
    if not recovery_execution.created_run_id:
        return VerificationVerdict(
            verdict_id=f"verdict:{uuid4().hex}",
            status=VerificationStatus.VERIFIED_UNKNOWN,
            summary=f"Recovery action {recovery_execution.action_name} executed but did not expose a created run id.",
            target_kind=EntityKind.RUN_TARGET,
            target_id=recovery_execution.run_target_id,
            evidence_refs=result_evidence_from_state(
                state,
                empty_summary_template=EMPTY_GOVERNED_RECOVERY_EVIDENCE,
            ),
        )
    created_governance = observation.created_governance if observation else None
    if created_governance is None:
        return VerificationVerdict(
            verdict_id=f"verdict:{uuid4().hex}",
            status=VerificationStatus.VERIFIED_UNKNOWN,
            summary=f"Created run {recovery_execution.created_run_id} could not be verified from governance snapshot.",
            target_kind=EntityKind.RUN_TARGET,
            target_id=recovery_execution.run_target_id,
            evidence_refs=result_evidence_from_state(
                state,
                empty_summary_template=EMPTY_GOVERNED_RECOVERY_EVIDENCE,
            ),
        )
    return VerificationVerdict(
        verdict_id=f"verdict:{uuid4().hex}",
        status=VerificationStatus.VERIFIED_SUCCESS,
        summary=f"Created run {recovery_execution.created_run_id} is readable from the latest governance snapshot.",
        target_kind=EntityKind.RUN_TARGET,
        target_id=recovery_execution.run_target_id,
        matched_check_ids=["created_run_exists"],
        evidence_refs=snapshot_evidence("get_run_governance_snapshot", recovery_execution.created_run_id),
    )


def verify_single_device_recovery(
    state: AgentRuntimeState,
    recovery_execution: RecoveryExecutionContext,
    observation: RecoveryObservationResult | None,
) -> VerificationVerdict:
    base_verdict = verify_create_run_recovery(state, recovery_execution, observation)
    if base_verdict.status != VerificationStatus.VERIFIED_SUCCESS:
        return base_verdict
    created_lineage = observation.created_lineage if observation else None
    if (
        created_lineage is None
        or recovery_execution.expected_device_id is None
        or not any(target.device_id == recovery_execution.expected_device_id for target in created_lineage.targets)
    ):
        return VerificationVerdict(
            verdict_id=f"verdict:{uuid4().hex}",
            status=VerificationStatus.VERIFIED_UNKNOWN,
            summary=(
                f"Created run {recovery_execution.created_run_id} exists, but the expected device binding "
                f"for {recovery_execution.expected_device_id or 'unknown-device'} could not be proven."
            ),
            target_kind=EntityKind.RUN_TARGET,
            target_id=recovery_execution.run_target_id,
            evidence_refs=result_evidence_from_state(
                state,
                empty_summary_template=EMPTY_GOVERNED_RECOVERY_EVIDENCE,
            ),
        )
    return VerificationVerdict(
        verdict_id=f"verdict:{uuid4().hex}",
        status=VerificationStatus.VERIFIED_SUCCESS,
        summary=(
            f"Created run {recovery_execution.created_run_id} exists and preserves the expected device binding "
            f"for {recovery_execution.expected_device_id}."
        ),
        target_kind=EntityKind.RUN_TARGET,
        target_id=recovery_execution.run_target_id,
        matched_check_ids=["created_run_exists", "device_binding_preserved"],
        evidence_refs=snapshot_evidence("get_run_lineage_snapshot", recovery_execution.created_run_id),
    )


__all__ = [
    "build_recovery_verification_spec",
    "prepare_blocked_reason",
    "verify_cancel_recovery",
    "verify_create_run_recovery",
    "verify_recovery",
    "verify_single_device_recovery",
]
