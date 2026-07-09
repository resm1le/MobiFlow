from __future__ import annotations

"""Recovery follow-up driver contracts and service."""

from pydantic import Field

from mobiflow_agent.execution.followup.decisions import RecoveryFollowupDriverDecision
from mobiflow_agent.common.contracts import StrictModel
from mobiflow_agent.execution.recovery.execution import GovernedRecoveryExecutionResponse
from mobiflow_agent.platform.adapter import PlatformAdapter
from mobiflow_agent.execution.followup.scheduling import (
    RecoveryFollowupDecision,
    RecoveryFollowupScheduleResponse,
    RecoveryFollowupSchedulingService,
    RecoveryFollowupSession,
)
from mobiflow_agent.execution.followup.outcome import RecoveryOutcomeFollowupResponse
from mobiflow_agent.runtime.state import RuntimeLifecycle

class RecoveryFollowupDriverJob(StrictModel):
    run_target_id: str = Field(min_length=1)
    source_run_id: str = Field(min_length=1)
    created_run_id: str = Field(min_length=1)
    action_name: str = Field(min_length=1)
    expected_device_id: str | None = None
    poll_count: int = Field(ge=1)
    max_polls: int = Field(ge=1)
    poll_interval_seconds: int = Field(ge=1)

class RecoveryFollowupDriverResponse(StrictModel):
    job: RecoveryFollowupDriverJob | None = None
    assessment: RecoveryOutcomeFollowupResponse | None = None
    decision: RecoveryFollowupDriverDecision
    next_poll_after_seconds: int | None = Field(default=None, ge=1)
    next_recovery_run_target_id: str | None = None
    summary: str = Field(min_length=1)

class RecoveryFollowupDriverService:
    def __init__(self, adapter: PlatformAdapter):
        self._scheduling_service = RecoveryFollowupSchedulingService(adapter)

    def start_from_execution(
        self,
        execution: GovernedRecoveryExecutionResponse,
        *,
        max_polls: int = 6,
        poll_interval_seconds: int = 30,
    ) -> RecoveryFollowupDriverResponse:
        self._validate_execution(execution)
        if execution.followup_required and not execution.created_run_id:
            raise ValueError("start_from_execution() requires created_run_id when followup_required is True.")
        if not execution.followup_required:
            return RecoveryFollowupDriverResponse(
                job=None,
                assessment=None,
                decision=RecoveryFollowupDriverDecision.NO_FOLLOWUP,
                next_poll_after_seconds=None,
                next_recovery_run_target_id=None,
                summary=(
                    execution.verdict.summary
                    if execution.verdict is not None
                    else f"Recovery execution for run target {execution.run_target_id} does not require follow-up."
                ),
            )

        schedule = self._scheduling_service.start(
            execution.run_target_id,
            execution.created_run_id,
            max_polls=max_polls,
            poll_interval_seconds=poll_interval_seconds,
        )
        return self._map_schedule_response(schedule)

    def tick(self, job: RecoveryFollowupDriverJob) -> RecoveryFollowupDriverResponse:
        self._validate_job(job)
        schedule = self._scheduling_service.tick(self._to_session(job))
        return self._map_schedule_response(schedule)

    @staticmethod
    def _validate_execution(execution: GovernedRecoveryExecutionResponse) -> None:
        if execution.lifecycle != RuntimeLifecycle.COMPLETED:
            raise ValueError("start_from_execution() requires a completed execution response.")

    @staticmethod
    def _validate_job(job: RecoveryFollowupDriverJob) -> None:
        if not job.run_target_id.strip():
            raise ValueError("tick() requires run_target_id.")
        if not job.source_run_id.strip():
            raise ValueError("tick() requires source_run_id.")
        if not job.created_run_id.strip():
            raise ValueError("tick() requires created_run_id.")
        if not job.action_name.strip():
            raise ValueError("tick() requires action_name.")
        if job.poll_count < 1 or job.max_polls < 1 or job.poll_interval_seconds < 1:
            raise ValueError("tick() requires positive poll_count, max_polls, and poll_interval_seconds.")
        if job.poll_count > job.max_polls:
            raise ValueError("tick() requires poll_count to be less than or equal to max_polls.")

    def _map_schedule_response(self, schedule: RecoveryFollowupScheduleResponse) -> RecoveryFollowupDriverResponse:
        decision_map = {
            RecoveryFollowupDecision.CONTINUE_POLLING: RecoveryFollowupDriverDecision.SCHEDULE_NEXT,
            RecoveryFollowupDecision.HANDOFF_ONLY: RecoveryFollowupDriverDecision.HANDOFF_ONLY,
            RecoveryFollowupDecision.STOP: RecoveryFollowupDriverDecision.COMPLETE,
        }
        driver_decision = decision_map[schedule.decision]
        return RecoveryFollowupDriverResponse(
            job=self._job_from_session(schedule.session) if driver_decision == RecoveryFollowupDriverDecision.SCHEDULE_NEXT else None,
            assessment=schedule.assessment,
            decision=driver_decision,
            next_poll_after_seconds=schedule.next_poll_after_seconds,
            next_recovery_run_target_id=schedule.next_recovery_run_target_id,
            summary=schedule.summary,
        )

    @staticmethod
    def _job_from_session(session: RecoveryFollowupSession) -> RecoveryFollowupDriverJob:
        return RecoveryFollowupDriverJob(
            run_target_id=session.run_target_id,
            source_run_id=session.source_run_id,
            created_run_id=session.created_run_id,
            action_name=session.action_name,
            expected_device_id=session.expected_device_id,
            poll_count=session.poll_count,
            max_polls=session.max_polls,
            poll_interval_seconds=session.poll_interval_seconds,
        )

    @staticmethod
    def _to_session(job: RecoveryFollowupDriverJob) -> RecoveryFollowupSession:
        return RecoveryFollowupSession(
            run_target_id=job.run_target_id,
            created_run_id=job.created_run_id,
            source_run_id=job.source_run_id,
            action_name=job.action_name,
            expected_device_id=job.expected_device_id,
            poll_count=job.poll_count,
            max_polls=job.max_polls,
            poll_interval_seconds=job.poll_interval_seconds,
        )
