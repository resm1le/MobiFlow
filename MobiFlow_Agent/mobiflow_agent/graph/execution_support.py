from __future__ import annotations

from mobiflow_agent.common.contracts import EvidenceKind, EvidenceRef, VerificationStatus, VerificationVerdict
from mobiflow_agent.platform.types import GovernedActionResult, GovernedActionState
from mobiflow_agent.runtime.state import CallerContext, ConfirmationState, PendingExecution
from mobiflow_agent.task.completion import TaskCompletionVerdict
from mobiflow_agent.task.session import TaskSession


class TaskGraphExecutionSupportMixin:
    @staticmethod
    def _set_execution_state(
        session: TaskSession,
        execution_result: GovernedActionResult,
        caller_context: CallerContext,
    ) -> None:
        session.last_execution_result = execution_result
        if execution_result.state != GovernedActionState.APPROVAL_REQUIRED:
            return
        proposal = (
            session.current_step.proposal
            if session.current_step is not None and session.current_step.proposal is not None
            else (session.last_step_decision.proposal if session.last_step_decision is not None else None)
        )
        if session.current_step is None or proposal is None:
            raise ValueError("Approval-required execution requires an active proposal step.")
        session.pending_execution = PendingExecution(
            proposal=proposal,
            caller_context=caller_context,
            confirmation_state=ConfirmationState.REQUIRED,
            confirmation_id=execution_result.confirmation_id,
            confirmation_summary=execution_result.confirmation_summary,
            confirmation_expires_at=execution_result.confirmation_expires_at,
            audit=execution_result.audit,
            entity_refs=execution_result.entity_refs,
        )

    @staticmethod
    def _clear_pending_execution(session: TaskSession) -> None:
        session.pending_execution = None

    def _execution_failure_verdict(
        self,
        session: TaskSession,
        execution_result: GovernedActionResult,
    ) -> VerificationVerdict:
        target_kind, target_id = self._focus(session)
        evidence_refs = []
        if execution_result.audit is not None:
            evidence_refs.append(
                EvidenceRef(
                    evidence_id=f"audit:{execution_result.audit.audit_id}",
                    kind=EvidenceKind.AUDIT,
                    summary=f"Governed action {execution_result.action_tool_name} produced audit evidence.",
                    locator=execution_result.audit.audit_id,
                )
            )
        if not evidence_refs:
            evidence_refs.append(
                EvidenceRef(
                    evidence_id=f"execution-note:{session.session_id}",
                    kind=EvidenceKind.INLINE_NOTE,
                    summary=f"Governed action {execution_result.action_tool_name} failed before verification.",
                    locator=target_id,
                )
            )
        return VerificationVerdict(
            verdict_id=f"task-verdict:{session.session_id}:execution-failed",
            status=VerificationStatus.VERIFIED_FAILED,
            summary=f"Governed action {execution_result.action_tool_name} failed before verification.",
            target_kind=target_kind,
            target_id=target_id,
            unmatched_check_ids=[session.active_verification_spec.success_checks[0].check_id]
            if session.active_verification_spec
            else ["has-evidence"],
            evidence_refs=evidence_refs,
        )

    def _approval_rejection_verdict(self, session: TaskSession, *, expired: bool) -> VerificationVerdict:
        target_kind, target_id = self._focus(session)
        blocked_reason = "approval_expired" if expired else "approval_rejected"
        proposal_name = (
            session.pending_execution.proposal.action_tool_name
            if session.pending_execution is not None
            else "unknown-action"
        )
        summary = (
            f"Approval for governed action {proposal_name} expired before execution."
            if expired
            else f"Approval for governed action {proposal_name} was rejected."
        )
        return VerificationVerdict(
            verdict_id=f"task-verdict:{session.session_id}:{blocked_reason}",
            status=VerificationStatus.BLOCKED,
            summary=summary,
            target_kind=target_kind,
            target_id=target_id,
            unmatched_check_ids=[session.active_verification_spec.success_checks[0].check_id]
            if session.active_verification_spec
            else ["has-evidence"],
            evidence_refs=[
                EvidenceRef(
                    evidence_id=f"approval-note:{session.session_id}",
                    kind=EvidenceKind.INLINE_NOTE,
                    summary=summary,
                    locator=target_id,
                )
            ],
            blocked_reason=blocked_reason,
        )

    @staticmethod
    def _map_completion(status: VerificationStatus) -> TaskCompletionVerdict:
        if status == VerificationStatus.BLOCKED:
            return TaskCompletionVerdict.BLOCKED
        if status == VerificationStatus.VERIFIED_FAILED:
            return TaskCompletionVerdict.FAILED
        if status == VerificationStatus.VERIFIED_SUCCESS:
            return TaskCompletionVerdict.TASK_COMPLETED
        return TaskCompletionVerdict.UNKNOWN


__all__ = ["TaskGraphExecutionSupportMixin"]
