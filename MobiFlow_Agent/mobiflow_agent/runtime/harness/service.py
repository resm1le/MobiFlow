from __future__ import annotations

from time import time
from uuid import uuid4

from mobiflow_agent.common.contracts import VerificationStatus
from mobiflow_agent.graph import TaskGraphRuntime
from mobiflow_agent.execution.followup.decisions import RecoveryFollowupDriverDecision
from mobiflow_agent.runtime.context import ContextHandoff
from mobiflow_agent.runtime.harness.errors import TaskHarnessError, TaskHarnessTransitionError
from mobiflow_agent.runtime.harness.models import (
    TASK_HARNESS_SCHEMA_VERSION,
    TaskHarnessApprovalRequest,
    TaskHarnessJob,
    TaskHarnessJobPolicy,
    TaskHarnessRequest,
    TaskHarnessResponse,
    TaskHarnessStatus,
)
from mobiflow_agent.runtime.harness.store import InMemoryTaskHarnessStore, TaskHarnessStore
from mobiflow_agent.runtime.state import AgentRuntimeState
from mobiflow_agent.task.plan import TaskStatus
from mobiflow_agent.task.session import TaskSession

TERMINAL_HARNESS_STATUSES = {
    TaskHarnessStatus.COMPLETED,
    TaskHarnessStatus.FAILED,
    TaskHarnessStatus.HANDED_OFF,
}


def build_task_harness_job_id() -> str:
    return f"harness-job:{uuid4().hex}"


class TaskHarnessService:
    def __init__(
        self,
        *,
        orchestrator: TaskGraphRuntime | None = None,
        store: TaskHarnessStore | None = None,
    ) -> None:
        self._orchestrator = orchestrator or TaskGraphRuntime()
        self._store = store or InMemoryTaskHarnessStore()

    @property
    def store(self) -> TaskHarnessStore:
        return self._store

    def start(self, request: TaskHarnessRequest) -> TaskHarnessResponse:
        now_ms = self._now_ms()
        job_id = build_task_harness_job_id()
        session = self._orchestrator.create_session(
            request.goal,
            target_kind=request.target_kind,
            target_id=request.target_id,
            proposal=request.proposal,
            verification_spec=request.verification_spec,
            handoff=request.handoff,
        )
        running_job = self._running_job(
            job_id=job_id,
            request=request,
            session=session,
            policy=request.policy,
            imported_handoff=request.handoff,
            heartbeat_attempts=0,
            now_ms=now_ms,
        )
        self._save_job(running_job)
        try:
            completed = self._orchestrator.run(session)
        except Exception as exc:  # pragma: no cover - exercised through tests with injected failures
            return self._persist_failure(job=running_job, error=exc, now_ms=now_ms)
        return self._persist_job_state(
            job=running_job,
            session=completed,
            now_ms=now_ms,
        )

    def resume_approval(
        self,
        job_id: str,
        *,
        approved: bool | None = None,
        expired: bool = False,
    ) -> TaskHarnessResponse:
        now_ms = self._now_ms()
        job = self.get_job(job_id)
        self._require_status(job, TaskHarnessStatus.AWAITING_APPROVAL, action="resume_approval")
        if job.session is None:
            raise TaskHarnessTransitionError(f"Task harness job {job_id} is missing the persisted session.")

        running_job = self._copy_job(
            job,
            status=TaskHarnessStatus.RUNNING,
            session=job.session.model_copy(deep=True),
            next_wakeup_at=None,
            updated_at_ms=now_ms,
        )
        self._save_job(running_job)
        try:
            session = self._orchestrator.resume(
                running_job.session.model_copy(deep=True),
                approved=approved,
                expired=expired,
            )
        except Exception as exc:
            return self._persist_failure(job=running_job, error=exc, now_ms=now_ms)
        return self._persist_job_state(job=running_job, session=session, now_ms=now_ms)

    def tick(self, job_id: str, *, now_ms: int | None = None) -> TaskHarnessResponse:
        resolved_now_ms = now_ms or self._now_ms()
        job = self.get_job(job_id)
        self._require_status(job, TaskHarnessStatus.SCHEDULED, action="tick")
        if job.next_wakeup_at is not None and job.next_wakeup_at > resolved_now_ms:
            raise TaskHarnessTransitionError(f"Task harness job {job_id} is not due yet.")
        if job.heartbeat_attempts >= job.policy.max_heartbeat_ticks:
            return self._mark_handed_off(
                job=job,
                summary=(
                    f"Heartbeat attempts reached the limit {job.policy.max_heartbeat_ticks}; "
                    "further follow-up requires manual handoff."
                ),
                now_ms=resolved_now_ms,
            )

        try:
            session = self._build_continuation_session(job)
        except TaskHarnessError:
            raise
        except Exception as exc:
            return self._persist_failure(job=job, error=exc, now_ms=resolved_now_ms)

        running_job = self._copy_job(
            job,
            status=TaskHarnessStatus.RUNNING,
            session=session,
            next_wakeup_at=None,
            heartbeat_attempts=job.heartbeat_attempts + 1,
            updated_at_ms=resolved_now_ms,
        )
        self._save_job(running_job)
        try:
            completed = self._orchestrator.run(session)
        except Exception as exc:
            return self._persist_failure(job=running_job, error=exc, now_ms=resolved_now_ms)
        return self._persist_job_state(
            job=running_job,
            session=completed,
            now_ms=resolved_now_ms,
        )

    def record_failure(
        self,
        job: TaskHarnessJob,
        *,
        error: BaseException | str,
        now_ms: int | None = None,
    ) -> TaskHarnessResponse:
        return self._persist_failure(job=job, error=error, now_ms=now_ms or self._now_ms())

    def get_job(self, job_id: str) -> TaskHarnessJob:
        return self._store.get_job(job_id)

    def export_handoff(self, job_id: str) -> ContextHandoff:
        job = self.get_job(job_id)
        if job.last_response is not None and job.last_response.context_handoff is not None:
            return job.last_response.context_handoff
        if job.imported_handoff is not None:
            return job.imported_handoff
        if job.session is None:
            raise TaskHarnessTransitionError(f"Task harness job {job_id} does not have a handoff candidate.")
        return self._orchestrator.export_context_handoff(job.session)

    def _build_continuation_session(self, job: TaskHarnessJob) -> TaskSession:
        if job.session is not None:
            return job.session.model_copy(deep=True)
        if job.imported_handoff is None:
            raise TaskHarnessTransitionError(f"Task harness job {job.job_id} has no continuation payload.")
        return self._orchestrator.create_session(
            (job.request.goal if job.request is not None else job.imported_handoff.goal),
            target_kind=(job.request.target_kind if job.request is not None else job.imported_handoff.target_kind),
            target_id=(job.request.target_id if job.request is not None else job.imported_handoff.target_id),
            proposal=job.request.proposal if job.request is not None else None,
            verification_spec=job.request.verification_spec if job.request is not None else None,
            handoff=job.imported_handoff,
        )

    def _persist_job_state(
        self,
        *,
        job: TaskHarnessJob,
        session: TaskSession,
        now_ms: int,
    ) -> TaskHarnessResponse:
        response = self._build_response(
            job_id=job.job_id,
            session=session,
            policy=job.policy,
            heartbeat_attempts=job.heartbeat_attempts,
            now_ms=now_ms,
        )
        persisted_session = session.model_copy(deep=True) if response.status == TaskHarnessStatus.AWAITING_APPROVAL else None
        next_imported_handoff = response.context_handoff or job.imported_handoff
        stored_job = self._copy_job(
            job,
            status=response.status,
            session=persisted_session,
            runtime_state=response.runtime_state,
            imported_handoff=next_imported_handoff,
            next_wakeup_at=response.next_wakeup_at,
            last_response=response,
            updated_at_ms=now_ms,
            last_error=response.error,
        )
        self._save_job(stored_job)
        return response

    def _build_response(
        self,
        *,
        job_id: str,
        session: TaskSession,
        policy: TaskHarnessJobPolicy,
        heartbeat_attempts: int,
        now_ms: int,
    ) -> TaskHarnessResponse:
        runtime_state = self._export_runtime_state(session)
        approval_request = self._approval_request_for_session(session)
        if session.status == TaskStatus.AWAITING_APPROVAL:
            return TaskHarnessResponse(
                job_id=job_id,
                session_id=session.session_id,
                status=TaskHarnessStatus.AWAITING_APPROVAL,
                completion_verdict=session.completion_verdict,
                runtime_state=runtime_state,
                approval_request=approval_request,
                latest_verdict=session.last_verdict,
                summary=approval_request.summary if approval_request is not None else "Task is awaiting approval.",
                heartbeat_attempts=heartbeat_attempts,
            )

        handoff = self._should_export_handoff(session)
        if handoff is not None:
            if policy.continue_on_handoff and heartbeat_attempts < policy.max_heartbeat_ticks:
                return TaskHarnessResponse(
                    job_id=job_id,
                    session_id=session.session_id,
                    status=TaskHarnessStatus.SCHEDULED,
                    completion_verdict=session.completion_verdict,
                    runtime_state=runtime_state,
                    context_handoff=handoff,
                    latest_verdict=session.last_verdict,
                    decision=RecoveryFollowupDriverDecision.SCHEDULE_NEXT,
                    summary=(
                        f"{self._summary_for_session(session)} Follow-up was scheduled for continued heartbeat polling."
                    ),
                    next_wakeup_at=now_ms + policy.wake_interval_seconds * 1000,
                    heartbeat_attempts=heartbeat_attempts,
                )
            return TaskHarnessResponse(
                job_id=job_id,
                session_id=session.session_id,
                status=TaskHarnessStatus.HANDED_OFF,
                completion_verdict=session.completion_verdict,
                runtime_state=runtime_state,
                context_handoff=handoff,
                latest_verdict=session.last_verdict,
                decision=RecoveryFollowupDriverDecision.HANDOFF_ONLY,
                summary=f"{self._summary_for_session(session)} Further progress now requires handoff.",
                heartbeat_attempts=heartbeat_attempts,
            )

        final_status = TaskHarnessStatus.COMPLETED if session.status == TaskStatus.COMPLETED else TaskHarnessStatus.FAILED
        return TaskHarnessResponse(
            job_id=job_id,
            session_id=session.session_id,
            status=final_status,
            completion_verdict=session.completion_verdict,
            runtime_state=runtime_state,
            latest_verdict=session.last_verdict,
            decision=RecoveryFollowupDriverDecision.COMPLETE,
            summary=self._summary_for_session(session),
            heartbeat_attempts=heartbeat_attempts,
        )

    def _mark_handed_off(
        self,
        *,
        job: TaskHarnessJob,
        summary: str,
        now_ms: int,
    ) -> TaskHarnessResponse:
        response = TaskHarnessResponse(
            job_id=job.job_id,
            session_id=self._session_id_for_job(job),
            status=TaskHarnessStatus.HANDED_OFF,
            completion_verdict=job.last_response.completion_verdict if job.last_response is not None else None,
            runtime_state=job.runtime_state,
            context_handoff=job.imported_handoff,
            approval_request=None,
            latest_verdict=job.last_response.latest_verdict if job.last_response is not None else None,
            decision=RecoveryFollowupDriverDecision.HANDOFF_ONLY,
            summary=summary,
            next_wakeup_at=None,
            heartbeat_attempts=job.heartbeat_attempts,
        )
        self._save_job(
            self._copy_job(
                job,
                status=TaskHarnessStatus.HANDED_OFF,
                next_wakeup_at=None,
                last_response=response,
                updated_at_ms=now_ms,
            )
        )
        return response

    def _persist_failure(
        self,
        *,
        job: TaskHarnessJob,
        error: BaseException | str,
        now_ms: int,
    ) -> TaskHarnessResponse:
        error_text = self._error_text(error)
        response = TaskHarnessResponse(
            job_id=job.job_id,
            session_id=self._session_id_for_job(job),
            status=TaskHarnessStatus.FAILED,
            completion_verdict=job.last_response.completion_verdict if job.last_response is not None else None,
            runtime_state=job.runtime_state,
            context_handoff=job.imported_handoff,
            latest_verdict=job.last_response.latest_verdict if job.last_response is not None else None,
            decision=job.last_response.decision if job.last_response is not None else None,
            summary=f"Task harness job failed: {error_text}",
            error=error_text,
            heartbeat_attempts=job.heartbeat_attempts,
        )
        failed_job = self._copy_job(
            job,
            status=TaskHarnessStatus.FAILED,
            session=None,
            next_wakeup_at=None,
            last_response=response,
            updated_at_ms=now_ms,
            last_error=error_text,
            failure_count=job.failure_count + 1,
        )
        self._save_job(failed_job)
        return response

    def _running_job(
        self,
        *,
        job_id: str,
        request: TaskHarnessRequest | None,
        session: TaskSession,
        policy: TaskHarnessJobPolicy,
        imported_handoff: ContextHandoff | None,
        heartbeat_attempts: int,
        now_ms: int,
    ) -> TaskHarnessJob:
        return TaskHarnessJob(
            job_id=job_id,
            schema_version=TASK_HARNESS_SCHEMA_VERSION,
            request=request,
            session=session.model_copy(deep=True),
            runtime_state=self._export_runtime_state(session),
            imported_handoff=imported_handoff,
            status=TaskHarnessStatus.RUNNING,
            next_wakeup_at=None,
            policy=policy,
            heartbeat_attempts=heartbeat_attempts,
            created_at_ms=now_ms,
            updated_at_ms=now_ms,
        )

    def _copy_job(self, job: TaskHarnessJob, **updates) -> TaskHarnessJob:
        data = job.model_dump(mode="python")
        data.update(updates)
        return TaskHarnessJob.model_validate(data)

    def _save_job(self, job: TaskHarnessJob) -> TaskHarnessJob:
        return self._store.save_job(job)

    def _require_status(self, job: TaskHarnessJob, expected: TaskHarnessStatus, *, action: str) -> None:
        if job.status in TERMINAL_HARNESS_STATUSES:
            raise TaskHarnessTransitionError(
                f"Task harness job {job.job_id} is terminal ({job.status.value}) and cannot run {action}()."
            )
        if job.status != expected:
            raise TaskHarnessTransitionError(
                f"Task harness job {job.job_id} must be {expected.value} before {action}(), "
                f"but is {job.status.value}."
            )

    def _should_export_handoff(self, session: TaskSession) -> ContextHandoff | None:
        if session.last_verdict is None:
            return None
        if session.last_verdict.status == VerificationStatus.VERIFIED_SUCCESS:
            return None
        return self._orchestrator.export_context_handoff(session)

    def _approval_request_for_session(self, session: TaskSession) -> TaskHarnessApprovalRequest | None:
        pending = session.pending_execution
        if pending is None or not pending.confirmation_id or not pending.confirmation_summary:
            return None
        return TaskHarnessApprovalRequest(
            confirmation_id=pending.confirmation_id,
            summary=pending.confirmation_summary,
            expires_at=pending.confirmation_expires_at,
        )

    def _export_runtime_state(self, session: TaskSession) -> AgentRuntimeState:
        return self._orchestrator.export_runtime_state(session)

    @staticmethod
    def _summary_for_session(session: TaskSession) -> str:
        if session.last_verdict is not None:
            return session.last_verdict.summary
        if session.pending_execution is not None and session.pending_execution.confirmation_summary:
            return session.pending_execution.confirmation_summary
        return f"Task session {session.session_id} finished in state {session.status.value}."

    @staticmethod
    def _session_id_for_job(job: TaskHarnessJob) -> str:
        if job.session is not None:
            return job.session.session_id
        if job.last_response is not None:
            return job.last_response.session_id
        return job.job_id

    @staticmethod
    def _error_text(error: BaseException | str) -> str:
        if isinstance(error, str):
            return error
        message = str(error).strip()
        return message or error.__class__.__name__

    @staticmethod
    def _now_ms() -> int:
        return int(time() * 1000)


__all__ = [
    "TERMINAL_HARNESS_STATUSES",
    "TaskHarnessService",
    "build_task_harness_job_id",
]
