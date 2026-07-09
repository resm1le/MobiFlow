from __future__ import annotations

from pydantic import Field

from mobiflow_agent.common.contracts import StrictModel, VerificationVerdict
from mobiflow_agent.runtime.state import AgentRuntimeState, RuntimeLifecycle


class GovernedRecoveryApproval(StrictModel):
    thread_id: str = Field(min_length=1)
    run_target_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    confirmation_id: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    expires_at: int | None = Field(default=None, ge=0)


class GovernedRecoveryExecutionResponse(StrictModel):
    thread_id: str = Field(min_length=1)
    run_target_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    action_name: str = Field(min_length=1)
    created_run_id: str | None = None
    followup_required: bool
    lifecycle: RuntimeLifecycle
    verdict: VerificationVerdict | None = None
    approval_request: GovernedRecoveryApproval | None = None
    runtime_state: AgentRuntimeState


__all__ = [
    "GovernedRecoveryApproval",
    "GovernedRecoveryExecutionResponse",
]
