from __future__ import annotations

from typing import Any

from pydantic import Field

from mobiflow_agent.common.contracts import StrictModel, VerificationVerdict
from mobiflow_agent.platform.types import GovernedActionResult, PlatformEntityRefs
from mobiflow_agent.runtime.state import (
    AgentRuntimeState,
    PendingExecution,
    RecoveryExecutionContext,
    RecoveryObservationResult,
    RuntimeLifecycle,
)


class GovernedActionEffect(StrictModel):
    created_run_id: str | None = None
    effective_run_id: str | None = None
    effective_target_ids: list[str] = Field(default_factory=list)


def parse_governed_action_effect(result: GovernedActionResult) -> GovernedActionEffect:
    executed_action = result.result.get("executedAction") if isinstance(result.result, dict) else None
    created_run_id = _parse_created_run_id(executed_action)
    effective_run_id = created_run_id or _parse_effective_run_id(executed_action, result.entity_refs)
    effective_target_ids = _parse_effective_target_ids(executed_action, result.entity_refs)
    return GovernedActionEffect(
        created_run_id=created_run_id,
        effective_run_id=effective_run_id,
        effective_target_ids=effective_target_ids,
    )


def _parse_created_run_id(executed_action: Any) -> str | None:
    if not isinstance(executed_action, dict):
        return None
    run = executed_action.get("run")
    if isinstance(run, dict):
        run_id = run.get("runId")
        if isinstance(run_id, str) and run_id.strip():
            return run_id
    return None


def _parse_effective_run_id(executed_action: Any, entity_refs: PlatformEntityRefs | None) -> str | None:
    if entity_refs is not None and entity_refs.run_id:
        return entity_refs.run_id
    if isinstance(executed_action, dict):
        run_id = executed_action.get("runId")
        if isinstance(run_id, str) and run_id.strip():
            return run_id
    return None


def _parse_effective_target_ids(executed_action: Any, entity_refs: PlatformEntityRefs | None) -> list[str]:
    target_ids: list[str] = []
    if entity_refs is not None and entity_refs.run_target_id:
        target_ids.append(entity_refs.run_target_id)
    if not isinstance(executed_action, dict):
        return target_ids

    targets = executed_action.get("targets")
    if isinstance(targets, list):
        for target in targets:
            if not isinstance(target, dict):
                continue
            run_target_id = target.get("runTargetId")
            if isinstance(run_target_id, str) and run_target_id.strip() and run_target_id not in target_ids:
                target_ids.append(run_target_id)
    return target_ids


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
    "AgentRuntimeState",
    "GovernedActionEffect",
    "GovernedRecoveryApproval",
    "GovernedRecoveryExecutionResponse",
    "PendingExecution",
    "RecoveryExecutionContext",
    "RecoveryObservationResult",
    "RuntimeLifecycle",
    "parse_governed_action_effect",
]
