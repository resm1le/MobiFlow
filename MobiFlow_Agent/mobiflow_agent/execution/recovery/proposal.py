from __future__ import annotations

"""Governed recovery proposal service under the execution namespace."""

from pydantic import Field

from mobiflow_agent.common.contracts import ExecutionProposal, StrictModel
from mobiflow_agent.platform.adapter import PlatformAdapter
from mobiflow_agent.platform.types import FailureTriageRecord, GovernedActionResult, RecoveryGuidance
from mobiflow_agent.execution.recovery.materializer import (
    MaterializedRecoveryAction,
    RecoveryMaterializationStatus,
    RecoveryProposalMaterializer,
)
from mobiflow_agent.runtime.state import CallerContext

class GovernedRecoveryProposalResponse(StrictModel):
    run_target_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    triage: FailureTriageRecord
    recovery_guidance: RecoveryGuidance
    materialization_status: RecoveryMaterializationStatus
    materialized_action: MaterializedRecoveryAction | None = None
    proposal: ExecutionProposal | None = None
    submission: GovernedActionResult | None = None
    missing_inputs: list[str] = Field(default_factory=list)
    blocked_reason: str | None = None
    summary: str = Field(min_length=1)

class GovernedRecoveryProposalService:
    def __init__(self, adapter: PlatformAdapter):
        self._adapter = adapter
        self._materializer = RecoveryProposalMaterializer()

    def prepare(self, run_target_id: str) -> GovernedRecoveryProposalResponse:
        run_target = self._adapter.get_run_target(run_target_id)
        run_id, attempt = self._resolve_run_context(run_target)
        triage = self._adapter.generate_failure_triage(run_target_id)
        guidance = self._adapter.get_recovery_guidance_context(run_id)
        governance_snapshot = self._adapter.get_run_governance_snapshot(run_id)
        lineage_snapshot = self._adapter.get_run_lineage_snapshot(run_id)
        catalog = self._adapter.get_tool_catalog()

        materialized = self._materializer.materialize(
            triage=triage,
            guidance=guidance,
            run_target=run_target,
            attempt=attempt,
            governance_snapshot=governance_snapshot,
            lineage_snapshot=lineage_snapshot,
            catalog=catalog,
        )
        return self._build_response(
            run_target_id=run_target_id,
            run_id=run_id,
            triage=triage,
            guidance=guidance,
            status=materialized.status,
            materialized_action=materialized.materialized_action,
            proposal=materialized.proposal,
            submission=None,
            missing_inputs=materialized.missing_inputs,
            blocked_reason=materialized.blocked_reason,
        )

    def submit(self, run_target_id: str) -> GovernedRecoveryProposalResponse:
        prepared = self.prepare(run_target_id)
        if prepared.materialization_status != RecoveryMaterializationStatus.READY or prepared.proposal is None:
            return prepared

        submission = self._adapter.submit_execution_proposal(
            prepared.proposal,
            self._caller_context(run_target_id),
        )
        return self._build_response(
            run_target_id=prepared.run_target_id,
            run_id=prepared.run_id,
            triage=prepared.triage,
            guidance=prepared.recovery_guidance,
            status=prepared.materialization_status,
            materialized_action=prepared.materialized_action,
            proposal=prepared.proposal,
            submission=submission,
            missing_inputs=prepared.missing_inputs,
            blocked_reason=prepared.blocked_reason,
        )

    def _resolve_run_context(self, run_target) -> tuple[str, object | None]:
        if run_target.latest_attempt is not None and run_target.latest_attempt.run_id:
            return run_target.latest_attempt.run_id, run_target.latest_attempt
        if run_target.latest_attempt_id:
            attempt = self._adapter.get_attempt(run_target.latest_attempt_id)
            return attempt.run_id, attempt
        raise ValueError(f"Could not resolve run_id for run target {run_target.run_target_id}.")

    @staticmethod
    def _caller_context(run_target_id: str) -> CallerContext:
        return CallerContext(
            session_id="mobiflow-agent",
            agent_task_id=f"recovery:{run_target_id}",
            turn_id="turn:0",
            step_id="submit",
        )

    def _build_response(
        self,
        *,
        run_target_id: str,
        run_id: str,
        triage: FailureTriageRecord,
        guidance: RecoveryGuidance,
        status: RecoveryMaterializationStatus,
        materialized_action: MaterializedRecoveryAction | None,
        proposal: ExecutionProposal | None,
        submission: GovernedActionResult | None,
        missing_inputs: list[str],
        blocked_reason: str | None,
    ) -> GovernedRecoveryProposalResponse:
        return GovernedRecoveryProposalResponse(
            run_target_id=run_target_id,
            run_id=run_id,
            triage=triage,
            recovery_guidance=guidance,
            materialization_status=status,
            materialized_action=materialized_action,
            proposal=proposal,
            submission=submission,
            missing_inputs=missing_inputs,
            blocked_reason=blocked_reason,
            summary=self._build_summary(
                run_target_id=run_target_id,
                triage=triage,
                guidance=guidance,
                status=status,
                materialized_action=materialized_action,
                submission=submission,
                missing_inputs=missing_inputs,
                blocked_reason=blocked_reason,
            ),
        )

    @staticmethod
    def _build_summary(
        *,
        run_target_id: str,
        triage: FailureTriageRecord,
        guidance: RecoveryGuidance,
        status: RecoveryMaterializationStatus,
        materialized_action: MaterializedRecoveryAction | None,
        submission: GovernedActionResult | None,
        missing_inputs: list[str],
        blocked_reason: str | None,
    ) -> str:
        action_name = guidance.recommended_action
        approval_hint = "approval required" if guidance.requires_approval else "no approval required"
        if submission is not None:
            return (
                f"Run target {run_target_id} triage is {triage.failure_category.value}: {triage.probable_cause}. "
                f"Recovery proposal for {action_name} was submitted with result {submission.state.value} ({approval_hint})."
            )
        if status == RecoveryMaterializationStatus.READY:
            return (
                f"Run target {run_target_id} triage is {triage.failure_category.value}: {triage.probable_cause}. "
                f"Recovery proposal for {action_name} is materialized and ready to submit ({approval_hint})."
            )
        if status == RecoveryMaterializationStatus.REQUIRES_INPUT:
            missing = ", ".join(missing_inputs)
            return (
                f"Run target {run_target_id} triage is {triage.failure_category.value}: {triage.probable_cause}. "
                f"Recovery proposal for {action_name} needs additional inputs: {missing}."
            )
        if status == RecoveryMaterializationStatus.OBSERVE_ONLY:
            return (
                f"Run target {run_target_id} triage is {triage.failure_category.value}: {triage.probable_cause}. "
                f"Recommended action is continue_observe ({approval_hint})."
            )
        reason = blocked_reason or (materialized_action.blocked_reason if materialized_action else "blocked")
        return (
            f"Run target {run_target_id} triage is {triage.failure_category.value}: {triage.probable_cause}. "
            f"Recovery proposal for {action_name} is blocked: {reason}."
        )
