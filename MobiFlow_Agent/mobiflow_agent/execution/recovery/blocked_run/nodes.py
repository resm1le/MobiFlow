from __future__ import annotations

from typing import Any
from uuid import uuid4

from mobiflow_agent.common.contracts import (
    ApprovalMode,
    EntityKind,
    EvidenceRef,
    ExecutionProposal,
    SuccessCriterion,
    TaskContract,
    VerificationCheck,
    VerificationSpec,
    VerificationStatus,
    VerificationVerdict,
)
from mobiflow_agent.execution.recovery.common import (
    finalize_lifecycle,
    result_evidence,
    result_evidence_from_state,
)
from mobiflow_agent.platform.adapter import PlatformAdapter
from mobiflow_agent.platform.evidence import (
    RUN_GOVERNANCE_FACT_ID,
    RUN_LINEAGE_FACT_ID,
    build_confirmation_evidence,
    get_fact,
    get_fact_value,
)
from mobiflow_agent.platform.types import GovernedActionState
from mobiflow_agent.runtime.state import (
    AgentRuntimeState,
    CallerContext,
    ConfirmationState,
    PendingExecution,
    RuntimeLifecycle,
)

EMPTY_BLOCKED_RUN_EVIDENCE = "Pending governed action {action_tool_name} has no platform evidence attached yet."


def ingest_request(state: AgentRuntimeState) -> dict[str, Any]:
    if state.focus_kind != EntityKind.RUN or not state.focus_id:
        raise ValueError("cancel_blocked_run_graph requires a run focus.")
    contract = state.active_contract or TaskContract(
        contract_id=f"contract:{state.focus_id}",
        user_goal=f"Cancel blocked run {state.focus_id} through the governed platform path.",
        outcome=f"Run {state.focus_id} enters CANCELLED state and the result is verified from governance state.",
        target_kind=EntityKind.RUN,
        target_id=state.focus_id,
        success_criteria=[
            SuccessCriterion(
                criterion_id="run_cancelled",
                description="Run status becomes CANCELLED in the governance snapshot.",
                evidence_hint="get_run_governance_snapshot",
            )
        ],
        verification_focus=["run_status", "blockers", "audit_refs"],
        approval_mode=ApprovalMode.ON_RISK,
    )
    verification = state.active_verification or build_cancel_verification_spec(state.focus_id)
    return {
        "active_contract": contract,
        "active_verification": verification,
        "lifecycle": RuntimeLifecycle.OBSERVING,
    }


def observe_run(state: AgentRuntimeState, adapter: PlatformAdapter) -> dict[str, Any]:
    observation = adapter.observe_run(state.focus_id)
    return {
        "latest_observation": observation,
        "known_resource_handles": observation.resource_handles,
        "lifecycle": RuntimeLifecycle.OBSERVING,
    }


def plan_cancel_run(state: AgentRuntimeState) -> dict[str, Any]:
    run_id = state.focus_id
    governance = get_fact_value(state.latest_observation, RUN_GOVERNANCE_FACT_ID) or {}
    lineage = get_fact_value(state.latest_observation, RUN_LINEAGE_FACT_ID) or {}
    blockers = governance.get("blockers") or []
    governed_options = lineage.get("currentGovernedOptions") or []

    if governance.get("status") != "BLOCKED" and not blockers:
        return {
            "latest_verdict": VerificationVerdict(
                verdict_id=f"verdict:{uuid4().hex}",
                status=VerificationStatus.BLOCKED,
                summary=f"Run {run_id} is not currently blocked, so the cancel-blocked-run chain does not apply.",
                target_kind=EntityKind.RUN,
                target_id=run_id,
                blocked_reason="run_not_blocked",
                evidence_refs=verdict_evidence(state.latest_observation, RUN_GOVERNANCE_FACT_ID),
            ),
            "lifecycle": RuntimeLifecycle.BLOCKED,
        }
    if "cancel_run" not in governed_options:
        return {
            "latest_verdict": VerificationVerdict(
                verdict_id=f"verdict:{uuid4().hex}",
                status=VerificationStatus.BLOCKED,
                summary=f"Run {run_id} is blocked but cancel_run is not currently allowed by platform governance.",
                target_kind=EntityKind.RUN,
                target_id=run_id,
                blocked_reason="cancel_run_not_allowed",
                evidence_refs=verdict_evidence(state.latest_observation, RUN_LINEAGE_FACT_ID),
            ),
            "lifecycle": RuntimeLifecycle.BLOCKED,
        }

    caller_context = CallerContext(
        session_id=state.session_id,
        agent_task_id=f"run:{run_id}",
        turn_id=f"turn:{state.turn_index}",
        step_id=f"step:{state.step_index + 1}",
    )
    proposal = ExecutionProposal(
        proposal_id=f"proposal:{uuid4().hex}",
        action_tool_name="cancel_run",
        arguments={"runId": run_id},
        target_kind=EntityKind.RUN,
        target_id=run_id,
        rationale=f"Run {run_id} is blocked and platform governance advertises cancel_run as an allowed governed action.",
        preconditions={"runId": run_id, "status": governance.get("status")},
        expected_observation_changes=["run status becomes CANCELLED", "blockers clear from governance snapshot"],
        confidence=0.87,
    )
    return {
        "pending_execution": PendingExecution(
            proposal=proposal,
            caller_context=caller_context,
        ),
        "active_verification": build_cancel_verification_spec(run_id),
    }


def submit_or_interrupt(state: AgentRuntimeState, adapter: PlatformAdapter) -> dict[str, Any]:
    pending = state.pending_execution
    if pending is None:
        raise ValueError("submit_or_interrupt requires a pending execution proposal.")

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
                summary=f"Governed action {pending.proposal.action_tool_name} failed before verification.",
                target_kind=EntityKind.RUN,
                target_id=state.focus_id,
                unmatched_check_ids=["run_cancelled"],
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
        "audit_refs": audit_refs,
        "lifecycle": RuntimeLifecycle.EXECUTING,
    }


def resume_after_approval(state: AgentRuntimeState, adapter: PlatformAdapter) -> dict[str, Any]:
    pending = state.pending_execution
    if pending is None:
        raise ValueError("resume_after_approval requires pending execution.")
    if not pending.confirmation_id:
        return {
            "latest_verdict": VerificationVerdict(
                verdict_id=f"verdict:{uuid4().hex}",
                status=VerificationStatus.BLOCKED,
                summary=f"Approval is required for proposal {pending.proposal.proposal_id}, but no confirmation id is present.",
                target_kind=EntityKind.RUN,
                target_id=state.focus_id,
                blocked_reason="missing_confirmation",
                evidence_refs=result_evidence_from_state(
                    state,
                    empty_summary_template=EMPTY_BLOCKED_RUN_EVIDENCE,
                ),
            ),
            "lifecycle": RuntimeLifecycle.BLOCKED,
        }
    if pending.confirmation_state == ConfirmationState.REQUIRED:
        return {
            "latest_verdict": VerificationVerdict(
                verdict_id=f"verdict:{uuid4().hex}",
                status=VerificationStatus.BLOCKED,
                summary=f"Approval for proposal {pending.proposal.proposal_id} is still pending required input.",
                target_kind=EntityKind.RUN,
                target_id=state.focus_id,
                blocked_reason="missing_confirmation",
                evidence_refs=result_evidence_from_state(
                    state,
                    empty_summary_template=EMPTY_BLOCKED_RUN_EVIDENCE,
                ),
            ),
            "lifecycle": RuntimeLifecycle.BLOCKED,
        }

    if pending.confirmation_state == ConfirmationState.EXPIRED:
        return {
            "latest_verdict": VerificationVerdict(
                verdict_id=f"verdict:{uuid4().hex}",
                status=VerificationStatus.BLOCKED,
                summary=f"Approval for proposal {pending.proposal.proposal_id} expired before execution.",
                target_kind=EntityKind.RUN,
                target_id=state.focus_id,
                blocked_reason="approval_expired",
                evidence_refs=result_evidence_from_state(
                    state,
                    empty_summary_template=EMPTY_BLOCKED_RUN_EVIDENCE,
                ),
            ),
            "lifecycle": RuntimeLifecycle.BLOCKED,
        }

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
                summary=f"Approval for proposal {pending.proposal.proposal_id} was rejected.",
                target_kind=EntityKind.RUN,
                target_id=state.focus_id,
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
                summary=f"Approval resolution for proposal {pending.proposal.proposal_id} did not produce an executable action.",
                target_kind=EntityKind.RUN,
                target_id=state.focus_id,
                unmatched_check_ids=[] if status == VerificationStatus.BLOCKED else ["run_cancelled"],
                blocked_reason=blocked_reason,
                evidence_refs=result_evidence(result),
            ),
            "lifecycle": RuntimeLifecycle.BLOCKED if status == VerificationStatus.BLOCKED else RuntimeLifecycle.COMPLETED,
        }
    return {
        "pending_execution": updated_pending,
        "audit_refs": [result.audit] if result.audit else state.audit_refs,
        "lifecycle": RuntimeLifecycle.EXECUTING,
    }


def reobserve_run(state: AgentRuntimeState, adapter: PlatformAdapter) -> dict[str, Any]:
    observation = adapter.observe_run(state.focus_id)
    return {
        "latest_observation": observation,
        "known_resource_handles": observation.resource_handles,
        "lifecycle": RuntimeLifecycle.VERIFYING,
    }


def verify_cancel_run(state: AgentRuntimeState) -> dict[str, Any]:
    governance_fact = get_fact(state.latest_observation, RUN_GOVERNANCE_FACT_ID)
    governance = governance_fact.value if governance_fact else {}
    evidence = governance_fact.evidence_refs if governance_fact else []
    status = governance.get("status")

    if status == "CANCELLED":
        verdict = VerificationVerdict(
            verdict_id=f"verdict:{uuid4().hex}",
            status=VerificationStatus.VERIFIED_SUCCESS,
            summary=f"Run {state.focus_id} is CANCELLED in the latest governance snapshot.",
            target_kind=EntityKind.RUN,
            target_id=state.focus_id,
            matched_check_ids=["run_cancelled"],
            evidence_refs=evidence,
        )
    elif status:
        verdict = VerificationVerdict(
            verdict_id=f"verdict:{uuid4().hex}",
            status=VerificationStatus.VERIFIED_FAILED,
            summary=f"Run {state.focus_id} is still {status} after the governed cancel action.",
            target_kind=EntityKind.RUN,
            target_id=state.focus_id,
            unmatched_check_ids=["run_cancelled"],
            evidence_refs=evidence,
        )
    else:
        fallback_evidence = evidence or result_evidence_from_state(
            state,
            empty_summary_template=EMPTY_BLOCKED_RUN_EVIDENCE,
        )
        verdict = VerificationVerdict(
            verdict_id=f"verdict:{uuid4().hex}",
            status=VerificationStatus.VERIFIED_UNKNOWN,
            summary=f"Cancel action completed but the latest observation could not prove whether run {state.focus_id} was cancelled.",
            target_kind=EntityKind.RUN,
            target_id=state.focus_id,
            evidence_refs=fallback_evidence,
        )
    return {
        "latest_verdict": verdict,
        "lifecycle": RuntimeLifecycle.COMPLETED if verdict.status != VerificationStatus.BLOCKED else RuntimeLifecycle.BLOCKED,
    }


def finalize(state: AgentRuntimeState) -> dict[str, Any]:
    return finalize_lifecycle(state)


def build_cancel_verification_spec(run_id: str) -> VerificationSpec:
    return VerificationSpec(
        verification_id=f"verification:{run_id}",
        target_kind=EntityKind.RUN,
        target_id=run_id,
        success_checks=[
            VerificationCheck(
                check_id="run_cancelled",
                description="Run status is CANCELLED in the latest governance snapshot.",
                evidence_hint="get_run_governance_snapshot",
            )
        ],
        blocked_conditions=["approval_rejected", "approval_expired", "missing_confirmation"],
    )


def verdict_evidence(observation, fact_id: str) -> list[EvidenceRef]:
    fact = get_fact(observation, fact_id)
    return fact.evidence_refs if fact else []


__all__ = [
    "EMPTY_BLOCKED_RUN_EVIDENCE",
    "build_cancel_verification_spec",
    "finalize",
    "ingest_request",
    "observe_run",
    "plan_cancel_run",
    "reobserve_run",
    "resume_after_approval",
    "submit_or_interrupt",
    "verdict_evidence",
    "verify_cancel_run",
]
