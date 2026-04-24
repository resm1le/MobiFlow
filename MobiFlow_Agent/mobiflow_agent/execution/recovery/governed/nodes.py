from __future__ import annotations

from typing import Any
from uuid import uuid4

from mobiflow_agent.common.contracts import (
    ApprovalMode,
    EntityKind,
    SuccessCriterion,
    TaskContract,
    VerificationStatus,
    VerificationVerdict,
)
from mobiflow_agent.execution.recovery.common import finalize_lifecycle
from mobiflow_agent.execution.recovery.governed.evidence import (
    EMPTY_GOVERNED_RECOVERY_EVIDENCE,
    inline_note_evidence,
    result_evidence,
    result_evidence_from_state,
    verification_check_ids,
)
from mobiflow_agent.execution.recovery.governed.models import parse_governed_action_effect
from mobiflow_agent.execution.recovery.governed.verification import (
    build_recovery_verification_spec,
    prepare_blocked_reason,
    verify_recovery as verify_recovery_outcome,
)
from mobiflow_agent.execution.recovery.materializer import RecoveryMaterializationStatus
from mobiflow_agent.execution.recovery.proposal import GovernedRecoveryProposalService
from mobiflow_agent.platform.adapter import PlatformAdapter, PlatformAdapterError
from mobiflow_agent.platform.evidence import build_confirmation_evidence
from mobiflow_agent.platform.types import GovernedActionResult, GovernedActionState
from mobiflow_agent.runtime.state import (
    AgentRuntimeState,
    CallerContext,
    ConfirmationState,
    PendingExecution,
    RecoveryExecutionContext,
    RecoveryObservationResult,
    RuntimeLifecycle,
)


def ingest_request(state: AgentRuntimeState) -> dict[str, Any]:
    if state.focus_kind != EntityKind.RUN_TARGET or not state.focus_id:
        raise ValueError("governed_recovery_execution_graph requires a run target focus.")
    contract = state.active_contract or TaskContract(
        contract_id=f"contract:{state.focus_id}",
        user_goal=f"Execute the governed recovery path for failed run target {state.focus_id}.",
        outcome=f"Recovery action for run target {state.focus_id} is governed, resumed if approved, and verified.",
        target_kind=EntityKind.RUN_TARGET,
        target_id=state.focus_id,
        success_criteria=[
            SuccessCriterion(
                criterion_id="recovery_action_effective",
                description="The governed recovery action has evidence that it took effect.",
                evidence_hint="governed action audit plus platform snapshots",
            )
        ],
        verification_focus=["governed_recovery", "approval_state", "platform_snapshots"],
        approval_mode=ApprovalMode.ON_RISK,
    )
    return {
        "active_contract": contract,
        "lifecycle": RuntimeLifecycle.OBSERVING,
    }


def prepare_recovery(
    state: AgentRuntimeState,
    proposal_service: GovernedRecoveryProposalService,
) -> dict[str, Any]:
    response = proposal_service.prepare(state.focus_id)
    action_name = (
        response.materialized_action.action_name
        if response.materialized_action is not None
        else response.recovery_guidance.recommended_action
    )
    recovery_execution = RecoveryExecutionContext(
        run_target_id=response.run_target_id,
        source_run_id=response.run_id,
        action_name=action_name,
        recommended_action=response.recovery_guidance.recommended_action,
        proposal_id=response.proposal.proposal_id if response.proposal is not None else f"proposal:{uuid4().hex}",
        expected_device_id=(
            response.materialized_action.arguments.get("deviceId")
            if response.materialized_action is not None
            else None
        ),
        created_run_id=None,
    )
    if response.materialization_status == RecoveryMaterializationStatus.READY and response.proposal is not None:
        caller_context = CallerContext(
            session_id=state.session_id,
            agent_task_id=f"recovery:{response.run_target_id}",
            turn_id=f"turn:{state.turn_index}",
            step_id=f"step:{state.step_index + 1}",
        )
        return {
            "pending_execution": PendingExecution(proposal=response.proposal, caller_context=caller_context),
            "recovery_execution": recovery_execution,
            "active_verification": build_recovery_verification_spec(recovery_execution),
            "lifecycle": RuntimeLifecycle.OBSERVING,
        }

    blocked_reason = prepare_blocked_reason(response.materialization_status, response.blocked_reason)
    return {
        "recovery_execution": recovery_execution,
        "latest_verdict": VerificationVerdict(
            verdict_id=f"verdict:{uuid4().hex}",
            status=VerificationStatus.BLOCKED,
            summary=response.summary,
            target_kind=EntityKind.RUN_TARGET,
            target_id=response.run_target_id,
            blocked_reason=blocked_reason,
            evidence_refs=inline_note_evidence(
                evidence_id=f"note:{response.run_target_id}:{blocked_reason}",
                summary=response.summary,
                locator=response.run_target_id,
            ),
        ),
        "lifecycle": RuntimeLifecycle.BLOCKED,
    }


def submit_or_interrupt(state: AgentRuntimeState, adapter: PlatformAdapter) -> dict[str, Any]:
    pending = state.pending_execution
    recovery_execution = state.recovery_execution
    if pending is None or recovery_execution is None:
        raise ValueError("submit_or_interrupt requires pending execution and recovery context.")

    result = adapter.submit_execution_proposal(pending.proposal, pending.caller_context)
    updated_pending = pending.model_copy(
        update={
            "audit": result.audit,
            "entity_refs": result.entity_refs,
            "confirmation_id": result.confirmation_id,
            "confirmation_summary": result.confirmation_summary,
            "confirmation_expires_at": result.confirmation_expires_at,
            "confirmation_state": (
                ConfirmationState.REQUIRED
                if result.state == GovernedActionState.APPROVAL_REQUIRED
                else ConfirmationState.APPROVED
            ),
        }
    )
    audit_refs = [result.audit] if result.audit else []

    if result.state == GovernedActionState.FAILED:
        return {
            "pending_execution": updated_pending,
            "audit_refs": audit_refs,
            "latest_verdict": VerificationVerdict(
                verdict_id=f"verdict:{uuid4().hex}",
                status=VerificationStatus.VERIFIED_FAILED,
                summary=f"Governed recovery action {pending.proposal.action_tool_name} failed before verification.",
                target_kind=EntityKind.RUN_TARGET,
                target_id=recovery_execution.run_target_id,
                unmatched_check_ids=verification_check_ids(state.active_verification),
                evidence_refs=result_evidence(result),
            ),
            "lifecycle": RuntimeLifecycle.COMPLETED,
        }

    if result.state == GovernedActionState.APPROVAL_REQUIRED:
        return {
            "pending_execution": updated_pending,
            "audit_refs": audit_refs,
            "lifecycle": RuntimeLifecycle.AWAITING_APPROVAL,
        }

    return {
        "pending_execution": updated_pending,
        "recovery_execution": apply_effect_to_context(recovery_execution, result),
        "audit_refs": audit_refs,
        "lifecycle": RuntimeLifecycle.EXECUTING,
    }


def resume_after_approval(state: AgentRuntimeState, adapter: PlatformAdapter) -> dict[str, Any]:
    pending = state.pending_execution
    recovery_execution = state.recovery_execution
    if pending is None or recovery_execution is None:
        raise ValueError("resume_after_approval requires pending execution and recovery context.")
    if not pending.confirmation_id:
        return blocked_from_state(state, "missing_confirmation", "Approval is required but no confirmation id is present.")
    if pending.confirmation_state == ConfirmationState.REQUIRED:
        return blocked_from_state(state, "missing_confirmation", "Approval input is still required before recovery can continue.")
    if pending.confirmation_state == ConfirmationState.EXPIRED:
        return blocked_from_state(state, "approval_expired", "Approval expired before the governed recovery action could execute.")
    if pending.confirmation_state == ConfirmationState.REJECTED:
        result = adapter.resolve_approval(pending.confirmation_id, False, pending.caller_context)
        evidence = result_evidence(result)
        if pending.confirmation_id and pending.confirmation_summary:
            evidence.append(build_confirmation_evidence(pending.confirmation_id, pending.confirmation_summary))
        return {
            "pending_execution": pending.model_copy(update={"audit": result.audit, "entity_refs": result.entity_refs}),
            "latest_verdict": VerificationVerdict(
                verdict_id=f"verdict:{uuid4().hex}",
                status=VerificationStatus.BLOCKED,
                summary=f"Approval for recovery proposal {pending.proposal.proposal_id} was rejected.",
                target_kind=EntityKind.RUN_TARGET,
                target_id=recovery_execution.run_target_id,
                blocked_reason="approval_rejected",
                evidence_refs=evidence,
            ),
            "audit_refs": [result.audit] if result.audit else state.audit_refs,
            "lifecycle": RuntimeLifecycle.BLOCKED,
        }

    result = adapter.resolve_approval(pending.confirmation_id, True, pending.caller_context)
    updated_pending = pending.model_copy(update={"audit": result.audit, "entity_refs": result.entity_refs})
    if result.state == GovernedActionState.FAILED:
        error_code = result.error.code if result.error else "approval_resolution_failed"
        status = (
            VerificationStatus.BLOCKED
            if error_code in {"TOOL_CONFIRMATION_INVALID", "CONFIRMATION_REJECTED"}
            else VerificationStatus.VERIFIED_FAILED
        )
        blocked_reason = "approval_invalid" if status == VerificationStatus.BLOCKED else None
        return {
            "pending_execution": updated_pending,
            "audit_refs": [result.audit] if result.audit else state.audit_refs,
            "latest_verdict": VerificationVerdict(
                verdict_id=f"verdict:{uuid4().hex}",
                status=status,
                summary=f"Approval resolution for recovery proposal {pending.proposal.proposal_id} did not produce an executable action.",
                target_kind=EntityKind.RUN_TARGET,
                target_id=recovery_execution.run_target_id,
                unmatched_check_ids=[] if status == VerificationStatus.BLOCKED else verification_check_ids(state.active_verification),
                blocked_reason=blocked_reason,
                evidence_refs=result_evidence(result),
            ),
            "lifecycle": RuntimeLifecycle.BLOCKED if status == VerificationStatus.BLOCKED else RuntimeLifecycle.COMPLETED,
        }
    return {
        "pending_execution": updated_pending,
        "recovery_execution": apply_effect_to_context(recovery_execution, result),
        "audit_refs": [result.audit] if result.audit else state.audit_refs,
        "lifecycle": RuntimeLifecycle.EXECUTING,
    }


def reobserve_recovery(state: AgentRuntimeState, adapter: PlatformAdapter) -> dict[str, Any]:
    recovery_execution = state.recovery_execution
    if recovery_execution is None:
        raise ValueError("reobserve_recovery requires recovery execution context.")

    observation = RecoveryObservationResult()
    if recovery_execution.action_name == "cancel_run":
        observation = observation.model_copy(
            update={
                "source_governance": safe_governance_read(adapter, recovery_execution.source_run_id),
                "source_lineage": safe_lineage_read(adapter, recovery_execution.source_run_id),
            }
        )
    elif recovery_execution.action_name in {"create_run", "create_single_device_run"}:
        if recovery_execution.created_run_id:
            observation = observation.model_copy(
                update={
                    "created_governance": safe_governance_read(adapter, recovery_execution.created_run_id),
                    "created_lineage": (
                        safe_lineage_read(adapter, recovery_execution.created_run_id)
                        if recovery_execution.action_name == "create_single_device_run"
                        else None
                    ),
                }
            )
    return {
        "recovery_observation": observation,
        "lifecycle": RuntimeLifecycle.VERIFYING,
    }


def verify_recovery(state: AgentRuntimeState) -> dict[str, Any]:
    recovery_execution = state.recovery_execution
    if recovery_execution is None:
        raise ValueError("verify_recovery requires recovery execution context.")
    verdict = verify_recovery_outcome(state, recovery_execution, state.recovery_observation)
    return {
        "latest_verdict": verdict,
        "lifecycle": RuntimeLifecycle.COMPLETED if verdict.status != VerificationStatus.BLOCKED else RuntimeLifecycle.BLOCKED,
    }


def finalize(state: AgentRuntimeState) -> dict[str, Any]:
    return finalize_lifecycle(state)


def apply_effect_to_context(
    recovery_execution: RecoveryExecutionContext,
    result: GovernedActionResult,
) -> RecoveryExecutionContext:
    effect = parse_governed_action_effect(result)
    return recovery_execution.model_copy(update={"created_run_id": effect.created_run_id or recovery_execution.created_run_id})


def safe_governance_read(adapter: PlatformAdapter, run_id: str):
    try:
        return adapter.get_run_governance_snapshot(run_id)
    except PlatformAdapterError:
        return None


def safe_lineage_read(adapter: PlatformAdapter, run_id: str):
    try:
        return adapter.get_run_lineage_snapshot(run_id)
    except PlatformAdapterError:
        return None


def blocked_from_state(
    state: AgentRuntimeState,
    blocked_reason: str,
    summary: str,
) -> dict[str, Any]:
    recovery_execution = state.recovery_execution
    target_id = recovery_execution.run_target_id if recovery_execution is not None else state.focus_id
    return {
        "latest_verdict": VerificationVerdict(
            verdict_id=f"verdict:{uuid4().hex}",
            status=VerificationStatus.BLOCKED,
            summary=summary,
            target_kind=EntityKind.RUN_TARGET,
            target_id=target_id,
            blocked_reason=blocked_reason,
            evidence_refs=result_evidence_from_state(
                state,
                empty_summary_template=EMPTY_GOVERNED_RECOVERY_EVIDENCE,
            ),
        ),
        "lifecycle": RuntimeLifecycle.BLOCKED,
    }


__all__ = [
    "apply_effect_to_context",
    "blocked_from_state",
    "finalize",
    "ingest_request",
    "prepare_recovery",
    "reobserve_recovery",
    "resume_after_approval",
    "safe_governance_read",
    "safe_lineage_read",
    "submit_or_interrupt",
    "verify_recovery",
]
