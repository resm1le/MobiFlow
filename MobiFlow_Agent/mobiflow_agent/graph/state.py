from __future__ import annotations

from pydantic import Field

from mobiflow_agent.common.contracts import StrictModel
from mobiflow_agent.task.session import TaskSession


class TaskGraphState(StrictModel):
    session: TaskSession
    resume_decision: bool | None = None
    resume_expired: bool = False
    last_error: str | None = None
    route_hint: str | None = Field(default=None)


__all__ = ["TaskGraphState"]
