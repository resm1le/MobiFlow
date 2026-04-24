from __future__ import annotations

"""Failure triage guidance service under the execution namespace."""

from pydantic import Field

from mobiflow_agent.common.contracts import StrictModel
from mobiflow_agent.platform.adapter import PlatformAdapter
from mobiflow_agent.platform.types import FailureTriageRecord, RecoveryGuidance

class FailureTriageGuidanceResponse(StrictModel):
    run_target_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    triage: FailureTriageRecord
    recovery_guidance: RecoveryGuidance
    summary: str = Field(min_length=1)

class FailureTriageGuidanceService:
    def __init__(self, adapter: PlatformAdapter):
        self._adapter = adapter

    def analyze(self, run_target_id: str) -> FailureTriageGuidanceResponse:
        run_target = self._adapter.get_run_target(run_target_id)
        run_id = self._resolve_run_id(run_target)
        triage = self._adapter.generate_failure_triage(run_target_id)
        guidance = self._adapter.get_recovery_guidance_context(run_id)
        return self._build_response(run_target_id, run_id, triage, guidance)

    def get_latest(self, run_target_id: str) -> FailureTriageGuidanceResponse:
        run_target = self._adapter.get_run_target(run_target_id)
        run_id = self._resolve_run_id(run_target)
        triage = self._adapter.get_latest_failure_triage(run_target_id)
        guidance = self._adapter.get_recovery_guidance_context(run_id)
        return self._build_response(run_target_id, run_id, triage, guidance)

    def _resolve_run_id(self, run_target) -> str:
        if run_target.latest_attempt is not None and run_target.latest_attempt.run_id:
            return run_target.latest_attempt.run_id
        if run_target.latest_attempt_id:
            attempt = self._adapter.get_attempt(run_target.latest_attempt_id)
            return attempt.run_id
        raise ValueError(f"Could not resolve run_id for run target {run_target.run_target_id}.")

    @staticmethod
    def _build_response(
        run_target_id: str,
        run_id: str,
        triage: FailureTriageRecord,
        guidance: RecoveryGuidance,
    ) -> FailureTriageGuidanceResponse:
        approval_hint = "approval required" if guidance.requires_approval else "no approval required"
        summary = (
            f"Run target {run_target_id} triage is {triage.failure_category.value}: {triage.probable_cause}. "
            f"Recommended next action is {guidance.recommended_action} ({approval_hint})."
        )
        return FailureTriageGuidanceResponse(
            run_target_id=run_target_id,
            run_id=run_id,
            triage=triage,
            recovery_guidance=guidance,
            summary=summary,
        )
