from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from pydantic import Field, field_validator, model_validator

from mobiflow_agent.agents.contracts import AgentRole
from mobiflow_agent.common.contracts import (
    DEFAULT_MOBILE_ACTIONS,
    PathConstraint,
    StrictModel,
)
from mobiflow_agent.intake.models import ExpectedOutcome, TaskIntakeStatus, TestCase
from mobiflow_agent.model.runtime import ModelRuntime
from mobiflow_agent.waypoint.catalog import SEQUENCE_ID_PATTERN
from mobiflow_agent.waypoint.models import (
    WaypointSequence,
    WaypointStrength,
)

if TYPE_CHECKING:
    from mobiflow_agent.waypoint.prompting import WaypointDraftPromptBuilder


class SequenceDraftSourceKind(str, Enum):
    NATURAL_LANGUAGE = "natural_language"
    LEGACY_SCRIPT = "legacy_script"


class SequenceDraftRequest(StrictModel):
    source_text: str = Field(min_length=1)
    source_kind: SequenceDraftSourceKind = SequenceDraftSourceKind.NATURAL_LANGUAGE
    sequence_id: str = Field(min_length=1)
    behavior_label: str = Field(min_length=1)
    profile_package: str = Field(min_length=1)

    @field_validator("source_text", "behavior_label", "profile_package")
    @classmethod
    def require_non_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Sequence draft text fields must not be blank.")
        return value

    @field_validator("sequence_id")
    @classmethod
    def require_versioned_sequence_id(cls, value: str) -> str:
        if not SEQUENCE_ID_PATTERN.fullmatch(value):
            raise ValueError("sequence_id must be a lowercase, explicit .vN identifier.")
        return value


class DraftWaypointCandidate(StrictModel):
    waypoint_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    arrival_outcomes: list[ExpectedOutcome] = Field(min_length=1)
    strength: WaypointStrength = WaypointStrength.COMMONSENSE
    path_constraint: PathConstraint | None = None
    allowed_actions: list[str] = Field(
        default_factory=lambda: list(DEFAULT_MOBILE_ACTIONS)
    )


class SequenceWaypointDraftCandidate(StrictModel):
    waypoints: list[DraftWaypointCandidate] = Field(min_length=1)


class SequenceDraftResult(StrictModel):
    status: TaskIntakeStatus
    sequence: WaypointSequence | None = None
    issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)
    trace_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_status_sequence(self) -> "SequenceDraftResult":
        if self.status == TaskIntakeStatus.READY and self.sequence is None:
            raise ValueError("READY sequence draft results require a sequence.")
        if self.status != TaskIntakeStatus.READY and self.sequence is not None:
            raise ValueError("Non-READY sequence draft results cannot carry a sequence.")
        return self


class WaypointDecompositionResult(StrictModel):
    accepted: bool
    candidate: SequenceWaypointDraftCandidate | None = None
    issues: list[str] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)
    trace_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_candidate(self) -> "WaypointDecompositionResult":
        if self.accepted and self.candidate is None:
            raise ValueError("Accepted waypoint decomposition requires a candidate.")
        if not self.accepted and self.candidate is not None:
            raise ValueError("Rejected waypoint decomposition cannot carry a candidate.")
        return self


class WaypointDraftDecomposer:
    def __init__(
        self,
        *,
        model_runtime: ModelRuntime | None = None,
        prompt_builder: WaypointDraftPromptBuilder | None = None,
        allowed_actions: tuple[str, ...] | None = None,
        profile_name: str | None = None,
    ) -> None:
        from mobiflow_agent.waypoint.prompting import WaypointDraftPromptBuilder

        self._model_runtime = model_runtime
        self._prompt_builder = prompt_builder or WaypointDraftPromptBuilder()
        self._allowed_actions = allowed_actions or DEFAULT_MOBILE_ACTIONS
        self._profile_name = profile_name

    def decompose(
        self,
        test_case: TestCase,
        *,
        request: SequenceDraftRequest,
        profile_name: str | None = None,
    ) -> WaypointDecompositionResult:
        if self._model_runtime is None:
            return WaypointDecompositionResult(
                accepted=False,
                issues=["waypoint_decomposition_model_runtime_missing"],
                clarification_questions=[
                    "需要模型运行时来把测试用例分解成逐航点到达条件。"
                ],
            )
        prompt = self._prompt_builder.build(
            test_case=test_case,
            request=request,
            allowed_actions=list(self._allowed_actions),
        )
        try:
            generated = self._model_runtime.generate_structured(
                role=AgentRole.TASK_INTERPRETER,
                prompt=prompt,
                response_model=SequenceWaypointDraftCandidate,
                profile_name=profile_name or self._profile_name,
                metadata={
                    "sequence_id": request.sequence_id,
                    "source_kind": request.source_kind.value,
                },
            )
        except Exception:
            return WaypointDecompositionResult(
                accepted=False,
                issues=["waypoint_decomposition_model_error"],
                clarification_questions=[
                    "无法把该用例可靠地分解为航点，请补充每个阶段的可观察到达条件。"
                ],
            )
        return WaypointDecompositionResult(
            accepted=True,
            candidate=generated.output,
            trace_refs=[generated.response.trace.invocation_id],
        )


__all__ = [
    "DraftWaypointCandidate",
    "SequenceDraftRequest",
    "SequenceDraftResult",
    "SequenceDraftSourceKind",
    "SequenceWaypointDraftCandidate",
    "WaypointDecompositionResult",
    "WaypointDraftDecomposer",
]
