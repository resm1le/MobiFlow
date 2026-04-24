from __future__ import annotations

from mobiflow_agent.common.contracts import VerificationStatus, VerificationVerdict
from mobiflow_agent.execution.followup.driver import RecoveryFollowupDriverDecision
from mobiflow_agent.runtime.harness import TaskHarnessResponse, TaskHarnessStatus
from mobiflow_agent.task.completion import TaskCompletionVerdict


def build_task_harness_response(
    *,
    decision: RecoveryFollowupDriverDecision = RecoveryFollowupDriverDecision.COMPLETE,
    verdict: VerificationVerdict | None = None,
    job_id: str = "harness-job:test",
    session_id: str = "session:test",
    summary: str = "harness summary",
) -> TaskHarnessResponse:
    status = {
        RecoveryFollowupDriverDecision.SCHEDULE_NEXT: TaskHarnessStatus.SCHEDULED,
        RecoveryFollowupDriverDecision.HANDOFF_ONLY: TaskHarnessStatus.HANDED_OFF,
        RecoveryFollowupDriverDecision.COMPLETE: TaskHarnessStatus.COMPLETED,
        RecoveryFollowupDriverDecision.NO_FOLLOWUP: TaskHarnessStatus.COMPLETED,
    }[decision]
    completion_verdict = None
    if verdict is not None:
        completion_verdict = {
            VerificationStatus.VERIFIED_SUCCESS: TaskCompletionVerdict.TASK_COMPLETED,
            VerificationStatus.VERIFIED_FAILED: TaskCompletionVerdict.FAILED,
            VerificationStatus.BLOCKED: TaskCompletionVerdict.BLOCKED,
            VerificationStatus.VERIFIED_UNKNOWN: TaskCompletionVerdict.UNKNOWN,
        }[verdict.status]
    return TaskHarnessResponse(
        job_id=job_id,
        session_id=session_id,
        status=status,
        completion_verdict=completion_verdict,
        latest_verdict=verdict,
        decision=decision,
        summary=summary,
        next_wakeup_at=30_000 if decision == RecoveryFollowupDriverDecision.SCHEDULE_NEXT else None,
    )
