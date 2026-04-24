from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from mobiflow_agent.agents.contracts import RecoveryOutcome, RoleRequest, RoleResult, StepDecision
from mobiflow_agent.common.contracts import (
    EntityKind,
    ExecutionProposal,
    ObservationView,
    StrictModel,
    TaskContract,
    VerificationSpec,
    VerificationVerdict,
)
from mobiflow_agent.model.telemetry import ModelInvocationTrace
from mobiflow_agent.platform.types import GovernedActionResult, RecoveryGuidance
from mobiflow_agent.runtime.context import ContextHandoff, SessionContextDigest, StepContextSummary
from mobiflow_agent.runtime.state import PendingExecution, RecoveryExecutionContext, RecoveryObservationResult
from mobiflow_agent.task.completion import TaskCompletionVerdict
from mobiflow_agent.task.plan import TaskPlan, TaskStatus, TaskStep


class TaskSession(StrictModel):
    session_id: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    status: TaskStatus = TaskStatus.CREATED
    status_history: list[TaskStatus] = Field(default_factory=lambda: [TaskStatus.CREATED])
    target_kind: EntityKind | None = None
    target_id: str | None = None
    initial_proposal: ExecutionProposal | None = None
    initial_verification_spec: VerificationSpec | None = None
    contract: TaskContract | None = None
    plan: TaskPlan | None = None
    current_step_index: int = Field(default=0, ge=0)
    current_step: TaskStep | None = None
    active_verification_spec: VerificationSpec | None = None
    last_observation: ObservationView | None = None
    last_execution_result: GovernedActionResult | None = None
    pending_execution: PendingExecution | None = None
    last_verdict: VerificationVerdict | None = None
    recovery_guidance: RecoveryGuidance | None = None
    recovery_execution: RecoveryExecutionContext | None = None
    recovery_observation: RecoveryObservationResult | None = None
    recovery_outcome: RecoveryOutcome | None = None
    step_policy_iterations: dict[str, int] = Field(default_factory=dict)
    step_decisions: list[StepDecision] = Field(default_factory=list)
    last_step_decision: StepDecision | None = None
    role_requests: list[RoleRequest] = Field(default_factory=list)
    role_results: list[RoleResult] = Field(default_factory=list)
    memory_context: dict[str, dict[str, Any]] = Field(default_factory=dict)
    evaluation_context: dict[str, dict[str, Any]] = Field(default_factory=dict)
    step_summaries: dict[str, StepContextSummary] = Field(default_factory=dict)
    session_digest: SessionContextDigest | None = None
    imported_handoff: ContextHandoff | None = None
    model_trace: list[ModelInvocationTrace] = Field(default_factory=list)
    active_model_profile: str | None = None
    recovery_state: str | None = None
    completion_verdict: TaskCompletionVerdict | None = None

    @model_validator(mode="after")
    def validate_step_alignment(self) -> "TaskSession":
        if self.target_id is not None and self.target_kind is None:
            raise ValueError("TaskSession target_id requires target_kind.")
        if self.current_step is not None and self.plan is None:
            raise ValueError("TaskSession current_step requires plan.")
        if self.plan is not None and self.current_step_index >= len(self.plan.steps):
            raise ValueError("TaskSession current_step_index is outside the active plan.")
        if self.plan is not None and self.current_step is not None:
            expected_step = self.plan.steps[self.current_step_index]
            if self.current_step.step_id != expected_step.step_id:
                raise ValueError("TaskSession current_step must align with the indexed step in the active plan.")
        return self
