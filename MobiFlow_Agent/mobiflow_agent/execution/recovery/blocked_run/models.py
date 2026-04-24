from __future__ import annotations

from pydantic import Field

from mobiflow_agent.common.contracts import StrictModel, VerificationVerdict
from mobiflow_agent.runtime.state import AgentRuntimeState, RuntimeLifecycle


class CancelBlockedRunApproval(StrictModel):
    thread_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    confirmation_id: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    expires_at: int | None = Field(default=None, ge=0)


class CancelBlockedRunResponse(StrictModel):
    thread_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    lifecycle: RuntimeLifecycle
    verdict: VerificationVerdict | None = None
    approval_request: CancelBlockedRunApproval | None = None
    runtime_state: AgentRuntimeState


__all__ = ["CancelBlockedRunApproval", "CancelBlockedRunResponse"]
