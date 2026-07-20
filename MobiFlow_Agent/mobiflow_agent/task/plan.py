from __future__ import annotations

from enum import Enum

from pydantic import Field, model_validator

from mobiflow_agent.common.contracts import EntityKind, ExecutionProposal, PathConstraint, StrictModel, VerificationSpec


class TaskStatus(str, Enum):
    CREATED = "created"
    PLANNING = "planning"
    OBSERVING = "observing"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    RECOVERING = "recovering"
    COMPLETED = "completed"
    FAILED = "failed"
    HANDED_OFF = "handed_off"


class TaskStepKind(str, Enum):
    DYNAMIC = "dynamic"
    RECOVER = "recover"


class TaskStepPolicy(StrictModel):
    policy_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    max_iterations: int = Field(default=3, ge=1)
    action_hints: list[str] = Field(default_factory=list)


class TaskStep(StrictModel):
    step_id: str = Field(min_length=1)
    kind: TaskStepKind
    goal: str = Field(min_length=1)
    preconditions: list[str] = Field(default_factory=list)
    expected_outputs: list[str] = Field(default_factory=list)
    verification_target_kind: EntityKind | None = None
    verification_target_id: str | None = None
    allowed_side_effects: list[str] = Field(default_factory=list)
    proposal: ExecutionProposal | None = None
    verification_spec: VerificationSpec | None = None
    path_constraint: PathConstraint | None = None
    policy: TaskStepPolicy | None = None

    @model_validator(mode="after")
    def validate_step(self) -> "TaskStep":
        if self.verification_target_id and self.verification_target_kind is None:
            raise ValueError("TaskStep verification_target_id requires verification_target_kind.")
        if self.proposal is not None and self.proposal.action_tool_name not in self.allowed_side_effects:
            raise ValueError("TaskStep allowed_side_effects must include the proposal action.")
        if self.kind == TaskStepKind.DYNAMIC and self.policy is None:
            raise ValueError("Dynamic TaskStep requires a step policy.")
        return self


class TaskPlan(StrictModel):
    plan_id: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    steps: list[TaskStep] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_steps(self) -> "TaskPlan":
        if not self.steps:
            raise ValueError("TaskPlan requires at least one step.")
        step_ids = [step.step_id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("TaskPlan step_id values must be unique.")
        return self
