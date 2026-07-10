from __future__ import annotations

from pydantic import Field

from mobiflow_agent.agents.contracts import AgentRole
from mobiflow_agent.common.contracts import (
    StrictModel,
    VerificationCheck,
    VerificationPredicate,
    VerificationPredicateOperator,
)
from mobiflow_agent.model.runtime import ModelRuntime

from .models import ExpectedOutcome, TestCase
from .prompting import AssertionSynthesizerPromptBuilder

PHASE_1_FACT_CATALOG = frozenset(
    {"mobile_observation_summary", "simulated_screen_snapshot", "simulated_ui_tree"}
)


class SynthesizedAssertion(StrictModel):
    check_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    evidence_hint: str | None = None
    predicates: list[VerificationPredicate] = Field(default_factory=list)


class AssertionSynthesisResult(StrictModel):
    accepted: bool
    checks: list[VerificationCheck] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)
    trace_refs: list[str] = Field(default_factory=list)


class AssertionSynthesizer:
    def __init__(
        self,
        *,
        model_runtime: ModelRuntime | None = None,
        prompt_builder: AssertionSynthesizerPromptBuilder | None = None,
        allowed_fact_ids: frozenset[str] | None = None,
        profile_name: str | None = None,
    ) -> None:
        self._model_runtime = model_runtime
        self._prompt_builder = prompt_builder or AssertionSynthesizerPromptBuilder()
        self._allowed_fact_ids = allowed_fact_ids or PHASE_1_FACT_CATALOG
        self._profile_name = profile_name

    def synthesize(self, test_case: TestCase) -> AssertionSynthesisResult:
        if self._model_runtime is None:
            return AssertionSynthesisResult(
                accepted=False,
                clarification_questions=["需要模型运行时来合成断言。"],
            )
        checks: list[VerificationCheck] = []
        trace_refs: list[str] = []
        for outcome in test_case.expected_outcomes:
            synthesized, refs, violation = self._synthesize_one(outcome)
            trace_refs.extend(refs)
            if synthesized is None:
                return AssertionSynthesisResult(
                    accepted=False,
                    issues=[violation or "assertion_synthesis_failed"],
                    clarification_questions=[
                        f"无法为预期结果生成可校验断言：{outcome.raw_text}。请补充更明确的可观察条件。"
                    ],
                    trace_refs=trace_refs,
                )
            checks.append(synthesized)
        return AssertionSynthesisResult(accepted=True, checks=checks, trace_refs=trace_refs)

    def _synthesize_one(
        self, outcome: ExpectedOutcome
    ) -> tuple[VerificationCheck | None, list[str], str | None]:
        refs: list[str] = []
        violation: str | None = None
        for attempt in range(2):
            prompt = self._prompt_builder.build(
                outcome_text=outcome.raw_text,
                allowed_fact_ids=sorted(self._allowed_fact_ids),
                allowed_operators=[op.value for op in VerificationPredicateOperator],
                violation=violation,
            )
            try:
                generated = self._model_runtime.generate_structured(
                    role=AgentRole.TASK_INTERPRETER,
                    prompt=prompt,
                    response_model=SynthesizedAssertion,
                    profile_name=self._profile_name,
                    metadata={"outcome_text": outcome.raw_text, "attempt": attempt},
                )
            except Exception:
                violation = "model_error"
                continue
            refs.append(generated.response.trace.invocation_id)
            violation = self._validate(generated.output)
            if violation is None:
                return self._to_check(generated.output), refs, None
        return None, refs, violation

    def _validate(self, assertion: SynthesizedAssertion) -> str | None:
        if not assertion.predicates:
            return "no_predicate"
        for predicate in assertion.predicates:
            if predicate.operator not in VerificationPredicateOperator:
                return f"illegal_operator:{predicate.operator}"
            if not predicate.field_path.strip():
                return "empty_field_path"
            if predicate.fact_id is None or predicate.fact_id not in self._allowed_fact_ids:
                return f"unknown_fact_id:{predicate.fact_id}"
        return None

    @staticmethod
    def _to_check(assertion: SynthesizedAssertion) -> VerificationCheck:
        return VerificationCheck(
            check_id=assertion.check_id,
            description=assertion.description,
            evidence_hint=assertion.evidence_hint,
            predicates=list(assertion.predicates),
        )


__all__ = [
    "AssertionSynthesisResult",
    "AssertionSynthesizer",
    "PHASE_1_FACT_CATALOG",
    "SynthesizedAssertion",
]
