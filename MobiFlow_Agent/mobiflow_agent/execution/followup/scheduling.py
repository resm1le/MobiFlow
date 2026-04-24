from __future__ import annotations

"""Recovery follow-up scheduling contracts and service."""

from enum import Enum

from pydantic import Field

from mobiflow_agent.common.contracts import EntityKind, StrictModel, VerificationStatus, VerificationVerdict
from mobiflow_agent.platform.adapter import PlatformAdapter
from mobiflow_agent.execution.followup.outcome import (
    RecoveryFollowupStatus,
    RecoveryOutcomeFollowupContext,
    RecoveryOutcomeFollowupResponse,
    RecoveryOutcomeFollowupService,
)

class RecoveryFollowupDecision(str, Enum):
    CONTINUE_POLLING = "continue_polling"
    HANDOFF_ONLY = "handoff_only"
    STOP = "stop"

class RecoveryFollowupSession(StrictModel):
    run_target_id: str = Field(min_length=1)
    created_run_id: str = Field(min_length=1)
    source_run_id: str = Field(min_length=1)
    action_name: str = Field(min_length=1)
    expected_device_id: str | None = None
    poll_count: int = Field(ge=1)
    max_polls: int = Field(ge=1)
    poll_interval_seconds: int = Field(ge=1)

class RecoveryFollowupScheduleResponse(StrictModel):
    session: RecoveryFollowupSession
    assessment: RecoveryOutcomeFollowupResponse
    decision: RecoveryFollowupDecision
    next_poll_after_seconds: int | None = Field(default=None, ge=1)
    next_recovery_run_target_id: str | None = None
    summary: str = Field(min_length=1)

class RecoveryFollowupSchedulingService:
    def __init__(self, adapter: PlatformAdapter):
        self._followup_service = RecoveryOutcomeFollowupService(adapter)

    def start(
        self,
        run_target_id: str,
        created_run_id: str,
        *,
        max_polls: int = 6,
        poll_interval_seconds: int = 30,
    ) -> RecoveryFollowupScheduleResponse:
        assessment = self._followup_service.assess(run_target_id, created_run_id)
        session = RecoveryFollowupSession(
            run_target_id=run_target_id,
            created_run_id=created_run_id,
            source_run_id=assessment.context.source_run_id,
            action_name=assessment.context.action_name,
            expected_device_id=assessment.context.expected_device_id,
            poll_count=1,
            max_polls=max_polls,
            poll_interval_seconds=poll_interval_seconds,
        )
        return self._build_schedule_response(session, assessment)

    def tick(self, session: RecoveryFollowupSession) -> RecoveryFollowupScheduleResponse:
        assessment = self._followup_service.assess(session.run_target_id, session.created_run_id)
        next_session = session.model_copy(update={"poll_count": session.poll_count + 1})
        return self._build_schedule_response(next_session, assessment)

    def _build_schedule_response(
        self,
        session: RecoveryFollowupSession,
        assessment: RecoveryOutcomeFollowupResponse,
    ) -> RecoveryFollowupScheduleResponse:
        final_assessment = assessment
        if assessment.status == RecoveryFollowupStatus.PENDING and session.poll_count >= session.max_polls:
            final_assessment = self._timed_out_assessment(assessment.context)

        if final_assessment.status == RecoveryFollowupStatus.PENDING:
            return RecoveryFollowupScheduleResponse(
                session=session,
                assessment=final_assessment,
                decision=RecoveryFollowupDecision.CONTINUE_POLLING,
                next_poll_after_seconds=session.poll_interval_seconds,
                next_recovery_run_target_id=None,
                summary=(
                    f"{final_assessment.summary} Poll again after {session.poll_interval_seconds} seconds "
                    f"(attempt {session.poll_count} of {session.max_polls})."
                ),
            )

        verdict = final_assessment.verdict
        if (
            verdict is not None
            and verdict.status in {VerificationStatus.BLOCKED, VerificationStatus.VERIFIED_FAILED}
            and final_assessment.next_recovery_run_target_id is not None
        ):
            return RecoveryFollowupScheduleResponse(
                session=session,
                assessment=final_assessment,
                decision=RecoveryFollowupDecision.HANDOFF_ONLY,
                next_poll_after_seconds=None,
                next_recovery_run_target_id=final_assessment.next_recovery_run_target_id,
                summary=(
                    f"{final_assessment.summary} Suggested next recovery follow-up handoff target is "
                    f"{final_assessment.next_recovery_run_target_id}."
                ),
            )

        return RecoveryFollowupScheduleResponse(
            session=session,
            assessment=final_assessment,
            decision=RecoveryFollowupDecision.STOP,
            next_poll_after_seconds=None,
            next_recovery_run_target_id=None,
            summary=final_assessment.summary,
        )

    @staticmethod
    def _timed_out_assessment(context: RecoveryOutcomeFollowupContext) -> RecoveryOutcomeFollowupResponse:
        summary = (
            f"Follow-up polling window for created run {context.created_run_id} was exhausted before the system "
            f"could prove whether the recovery outcome continued to progress."
        )
        return RecoveryOutcomeFollowupResponse(
            status=RecoveryFollowupStatus.COMPLETED,
            context=context,
            verdict=VerificationVerdict(
                verdict_id=f"verdict:followup:{context.created_run_id}:timeout",
                status=VerificationStatus.VERIFIED_UNKNOWN,
                summary=summary,
                target_kind=EntityKind.RUN_TARGET,
                target_id=context.run_target_id,
            ),
            next_recovery_run_target_id=None,
            summary=summary,
        )
