from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from pydantic import Field, field_validator, model_validator

from mobiflow_agent.agents.contracts import AgentRole
from mobiflow_agent.common.contracts import (
    DEFAULT_MOBILE_ACTIONS,
    EntityKind,
    PathConstraint,
    StrictModel,
    VerificationSpec,
)
from mobiflow_agent.intake.interpreter import TestCaseParser
from mobiflow_agent.intake.models import ExpectedOutcome, TaskIntakeStatus, TestCase
from mobiflow_agent.intake.synthesizer import AssertionSynthesizer
from mobiflow_agent.model.runtime import ModelRuntime
from mobiflow_agent.waypoint.catalog import SEQUENCE_ID_PATTERN
from mobiflow_agent.waypoint.models import (
    Waypoint,
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
        self._allowed_actions = (
            DEFAULT_MOBILE_ACTIONS if allowed_actions is None else allowed_actions
        )
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


class SequenceDraftService:
    def __init__(
        self,
        *,
        model_runtime: ModelRuntime | None = None,
        parser: TestCaseParser | None = None,
        decomposer: WaypointDraftDecomposer | None = None,
        synthesizer: AssertionSynthesizer | None = None,
        allowed_actions: tuple[str, ...] | None = None,
        profile_name: str | None = None,
    ) -> None:
        self._allowed_actions = (
            DEFAULT_MOBILE_ACTIONS if allowed_actions is None else allowed_actions
        )
        self._profile_name = profile_name
        self._parser = parser or TestCaseParser(model_runtime=model_runtime)
        self._decomposer = decomposer or WaypointDraftDecomposer(
            model_runtime=model_runtime,
            allowed_actions=self._allowed_actions,
            profile_name=profile_name,
        )
        self._synthesizer = synthesizer or AssertionSynthesizer(
            model_runtime=model_runtime,
            profile_name=profile_name,
        )

    def draft_sequence(self, request: SequenceDraftRequest) -> SequenceDraftResult:
        trace_refs: list[str] = []
        parsed = self._parser.parse(
            request.source_text,
            platform_context={
                "sequence_draft_source_kind": request.source_kind.value,
            },
            profile_name=self._profile_name,
        )
        trace_refs.extend(parsed.trace_refs)
        if parsed.test_case is None:
            status = (
                TaskIntakeStatus.REJECTED
                if parsed.status == TaskIntakeStatus.REJECTED
                else TaskIntakeStatus.NEEDS_CLARIFICATION
            )
            return SequenceDraftResult(
                status=status,
                issues=list(parsed.issues),
                clarification_questions=list(parsed.clarification_questions),
                trace_refs=_dedupe(trace_refs),
            )

        test_case = parsed.test_case
        warnings = _dedupe(
            [f"execution_risk:{risk_flag}" for risk_flag in test_case.risk_flags]
        )
        input_issues = self._validate_test_case_actions(test_case)
        if input_issues:
            return SequenceDraftResult(
                status=TaskIntakeStatus.REJECTED,
                issues=input_issues,
                warnings=warnings,
                trace_refs=_dedupe(trace_refs),
            )

        decomposition = self._decomposer.decompose(
            test_case,
            request=request,
            profile_name=self._profile_name,
        )
        trace_refs.extend(decomposition.trace_refs)
        if not decomposition.accepted or decomposition.candidate is None:
            return SequenceDraftResult(
                status=TaskIntakeStatus.NEEDS_CLARIFICATION,
                issues=list(decomposition.issues),
                warnings=warnings,
                clarification_questions=list(decomposition.clarification_questions),
                trace_refs=_dedupe(trace_refs),
            )

        candidate_issues = self._validate_candidate(decomposition.candidate)
        if candidate_issues:
            return SequenceDraftResult(
                status=TaskIntakeStatus.REJECTED,
                issues=candidate_issues,
                warnings=warnings,
                trace_refs=_dedupe(trace_refs),
            )

        waypoints: list[Waypoint] = []
        for candidate in decomposition.candidate.waypoints:
            waypoint_case = TestCase(
                case_id=f"{test_case.case_id}:{candidate.waypoint_id}",
                raw_goal=test_case.raw_goal,
                normalized_goal=candidate.description,
                expected_outcomes=[
                    outcome.model_copy(deep=True)
                    for outcome in candidate.arrival_outcomes
                ],
                target_app=test_case.target_app,
                approval_mode=test_case.approval_mode,
                risk_flags=list(test_case.risk_flags),
                confidence=test_case.confidence,
                needs_confirmation=test_case.needs_confirmation,
            )
            synthesis = self._synthesizer.synthesize(waypoint_case)
            trace_refs.extend(synthesis.trace_refs)
            if not synthesis.accepted:
                issues = [
                    f"waypoint:{candidate.waypoint_id}:{issue}"
                    for issue in synthesis.issues
                ] or [f"waypoint:{candidate.waypoint_id}:assertion_synthesis_failed"]
                return SequenceDraftResult(
                    status=TaskIntakeStatus.NEEDS_CLARIFICATION,
                    issues=issues,
                    warnings=warnings,
                    clarification_questions=list(synthesis.clarification_questions),
                    trace_refs=_dedupe(trace_refs),
                )
            check_ids = [check.check_id for check in synthesis.checks]
            duplicate_check_ids = _duplicates(check_ids)
            if duplicate_check_ids:
                return SequenceDraftResult(
                    status=TaskIntakeStatus.REJECTED,
                    issues=[
                        f"waypoint:{candidate.waypoint_id}:duplicate_check_id:{check_id}"
                        for check_id in duplicate_check_ids
                    ],
                    warnings=warnings,
                    trace_refs=_dedupe(trace_refs),
                )
            arrival_spec = VerificationSpec(
                verification_id=(
                    f"verification:task:{candidate.waypoint_id}:arrival"
                ),
                target_kind=EntityKind.TASK,
                target_id=candidate.waypoint_id,
                success_checks=list(synthesis.checks),
            )
            waypoints.append(
                Waypoint(
                    waypoint_id=candidate.waypoint_id,
                    description=candidate.description,
                    arrival_spec=arrival_spec,
                    strength=candidate.strength,
                    path_constraint=candidate.path_constraint,
                    allowed_actions=list(candidate.allowed_actions),
                )
            )

        sequence = WaypointSequence(
            sequence_id=request.sequence_id,
            behavior_label=request.behavior_label,
            profile_package=request.profile_package,
            waypoints=waypoints,
        )
        return SequenceDraftResult(
            status=TaskIntakeStatus.READY,
            sequence=sequence,
            warnings=warnings,
            trace_refs=_dedupe(trace_refs),
        )

    def _validate_test_case_actions(self, test_case: TestCase) -> list[str]:
        allowed_actions = set(self._allowed_actions)
        return _dedupe(
            [
                f"disallowed_action:{step.hint_action}"
                for step in test_case.steps
                if step.hint_action is not None
                and step.hint_action not in allowed_actions
            ]
        )

    def _validate_candidate(
        self,
        candidate: SequenceWaypointDraftCandidate,
    ) -> list[str]:
        issues: list[str] = []
        waypoint_ids = [waypoint.waypoint_id for waypoint in candidate.waypoints]
        issues.extend(
            f"duplicate_waypoint_id:{waypoint_id}"
            for waypoint_id in _duplicates(waypoint_ids)
        )
        allowed_actions = set(self._allowed_actions)
        for waypoint in candidate.waypoints:
            if not waypoint.waypoint_id.strip():
                issues.append("invalid_waypoint_id")
            for action in waypoint.allowed_actions:
                if action not in allowed_actions:
                    issues.append(
                        f"waypoint:{waypoint.waypoint_id}:disallowed_action:{action}"
                    )
        return _dedupe(issues)


def _duplicates(values: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return duplicates


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


__all__ = [
    "DraftWaypointCandidate",
    "SequenceDraftRequest",
    "SequenceDraftResult",
    "SequenceDraftService",
    "SequenceDraftSourceKind",
    "SequenceWaypointDraftCandidate",
    "WaypointDecompositionResult",
    "WaypointDraftDecomposer",
]
