from __future__ import annotations

from time import time

from mobiflow_agent.runtime.harness.models import TaskHarnessResponse
from mobiflow_agent.runtime.harness.service import TaskHarnessService


class TaskHeartbeatRunner:
    def __init__(self, service: TaskHarnessService) -> None:
        self._service = service

    def run_once(self, *, now_ms: int | None = None, limit: int = 20) -> list[TaskHarnessResponse]:
        resolved_now_ms = now_ms or int(time() * 1000)
        due_jobs = self._service.store.list_due_jobs(now_ms=resolved_now_ms, limit=limit)
        responses: list[TaskHarnessResponse] = []
        for job in due_jobs:
            try:
                responses.append(self._service.tick(job.job_id, now_ms=resolved_now_ms))
            except Exception as exc:
                responses.append(self._service.record_failure(job, error=exc, now_ms=resolved_now_ms))
        return responses


__all__ = ["TaskHeartbeatRunner"]
