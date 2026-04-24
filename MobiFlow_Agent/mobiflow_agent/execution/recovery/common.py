from __future__ import annotations

"""Shared helpers for governed recovery execution flows."""

from collections.abc import Mapping
from typing import Any

from langgraph.types import Command

from mobiflow_agent.common.contracts import EvidenceKind, EvidenceRef, VerificationSpec
from mobiflow_agent.platform.evidence import build_confirmation_evidence
from mobiflow_agent.platform.types import GovernedActionResult
from mobiflow_agent.runtime.state import (
    AgentRuntimeState,
    ConfirmationState,
    PendingExecution,
    RuntimeLifecycle,
)


def resume_pending_execution(
    app: Any,
    config: dict[str, Any],
    persisted_state: AgentRuntimeState | Mapping[str, Any],
    *,
    approved: bool | None = None,
    expired: bool = False,
    missing_pending_message: str,
    missing_decision_message: str,
):
    pending_payload = (
        persisted_state.pending_execution
        if isinstance(persisted_state, AgentRuntimeState)
        else persisted_state.get("pending_execution")
    )
    if pending_payload is None:
        raise ValueError(missing_pending_message)

    pending = (
        pending_payload
        if isinstance(pending_payload, PendingExecution)
        else PendingExecution.model_validate(pending_payload)
    )
    if expired:
        confirmation_state = ConfirmationState.EXPIRED
    elif approved is True:
        confirmation_state = ConfirmationState.APPROVED
    elif approved is False:
        confirmation_state = ConfirmationState.REJECTED
    else:
        raise ValueError(missing_decision_message)

    return app.invoke(
        Command(
            update={
                "pending_execution": pending.model_copy(update={"confirmation_state": confirmation_state}),
                "lifecycle": RuntimeLifecycle.AWAITING_APPROVAL,
            }
        ),
        config=config,
    )


def finalize_lifecycle(state: AgentRuntimeState) -> dict[str, RuntimeLifecycle]:
    verdict = state.latest_verdict
    if verdict is None:
        return {}
    if verdict.status.value == "blocked":
        return {"lifecycle": RuntimeLifecycle.BLOCKED}
    return {"lifecycle": RuntimeLifecycle.COMPLETED}


def verification_check_ids(verification: VerificationSpec | None) -> list[str]:
    if verification is None:
        return []
    return [check.check_id for check in verification.success_checks]


def snapshot_evidence(tool_name: str, run_id: str) -> list[EvidenceRef]:
    return [
        EvidenceRef(
            evidence_id=f"snapshot:{tool_name}:run:{run_id}",
            kind=EvidenceKind.PLATFORM_SNAPSHOT,
            summary=f"{tool_name} for run {run_id}.",
            locator=run_id,
        )
    ]


def inline_note_evidence(evidence_id: str, summary: str, locator: str) -> list[EvidenceRef]:
    return [
        EvidenceRef(
            evidence_id=evidence_id,
            kind=EvidenceKind.INLINE_NOTE,
            summary=summary,
            locator=locator,
        )
    ]


def result_evidence(result: GovernedActionResult) -> list[EvidenceRef]:
    evidence: list[EvidenceRef] = []
    if result.audit is not None:
        evidence.append(
            EvidenceRef(
                evidence_id=f"audit:{result.audit.audit_id}",
                kind=EvidenceKind.AUDIT,
                summary=f"Tool audit {result.audit.audit_id}.",
                locator=result.audit.audit_id,
            )
        )
    if result.confirmation_id and result.confirmation_summary:
        evidence.append(build_confirmation_evidence(result.confirmation_id, result.confirmation_summary))
    if not evidence:
        locator = result.proposal_id
        summary = result.error.message if result.error else f"Governed action {result.action_tool_name} returned no evidence payload."
        evidence.append(
            EvidenceRef(
                evidence_id=f"note:{locator}",
                kind=EvidenceKind.INLINE_NOTE,
                summary=summary,
                locator=locator,
            )
        )
    return evidence


def result_evidence_from_state(
    state: AgentRuntimeState,
    *,
    empty_summary_template: str,
) -> list[EvidenceRef]:
    pending = state.pending_execution
    if pending is None:
        return []
    evidence: list[EvidenceRef] = []
    if pending.audit is not None:
        evidence.append(
            EvidenceRef(
                evidence_id=f"audit:{pending.audit.audit_id}",
                kind=EvidenceKind.AUDIT,
                summary=f"Tool audit {pending.audit.audit_id}.",
                locator=pending.audit.audit_id,
            )
        )
    if pending.confirmation_id and pending.confirmation_summary:
        evidence.append(build_confirmation_evidence(pending.confirmation_id, pending.confirmation_summary))
    if not evidence:
        evidence.append(
            EvidenceRef(
                evidence_id=f"note:{pending.proposal.proposal_id}",
                kind=EvidenceKind.INLINE_NOTE,
                summary=empty_summary_template.format(action_tool_name=pending.proposal.action_tool_name),
                locator=pending.proposal.proposal_id,
            )
        )
    return evidence
