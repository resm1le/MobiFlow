from __future__ import annotations

"""Benchmark suite assets and service."""

from enum import Enum
from uuid import uuid4

from pydantic import Field, model_validator

from mobiflow_agent.common.contracts import StrictModel, VerificationStatus
from mobiflow_agent.memory.case import RecoveryMemoryCase
from mobiflow_agent.execution.followup.driver import RecoveryFollowupDriverDecision
from mobiflow_agent.evaluation.replay import RecoveryEvalCase

class RecoveryBenchmarkSchemaVersion(str, Enum):
    V1 = "v1"

class RecoveryBenchmarkCase(StrictModel):
    schema_version: RecoveryBenchmarkSchemaVersion = RecoveryBenchmarkSchemaVersion.V1
    benchmark_case_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    category: str = Field(min_length=1)
    eval_case: RecoveryEvalCase
    memory_case: RecoveryMemoryCase | None = None

class RecoveryBenchmarkSuite(StrictModel):
    schema_version: RecoveryBenchmarkSchemaVersion = RecoveryBenchmarkSchemaVersion.V1
    suite_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    cases: list[RecoveryBenchmarkCase] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_cases(self) -> "RecoveryBenchmarkSuite":
        if not self.cases:
            raise ValueError("RecoveryBenchmarkSuite requires at least one case.")
        return self

class RecoveryBenchmarkCaseResult(StrictModel):
    benchmark_case_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    matched: bool
    actual_decision: RecoveryFollowupDriverDecision
    actual_verdict_status: VerificationStatus | None = None
    summary: str = Field(min_length=1)

class RecoveryBenchmarkReport(StrictModel):
    schema_version: RecoveryBenchmarkSchemaVersion = RecoveryBenchmarkSchemaVersion.V1
    suite_id: str = Field(min_length=1)
    suite_name: str = Field(min_length=1)
    total_cases: int = Field(ge=0)
    matched_cases: int = Field(ge=0)
    mismatched_cases: int = Field(ge=0)
    match_rate: float = Field(ge=0.0, le=1.0)
    results: list[RecoveryBenchmarkCaseResult] = Field(default_factory=list)
    summary: str = Field(min_length=1)

def build_benchmark_case_id() -> str:
    return f"benchmark-case:{uuid4().hex}"

def build_benchmark_suite_id() -> str:
    return f"benchmark-suite:{uuid4().hex}"

from mobiflow_agent.memory.case import RecoveryMemoryCase
from mobiflow_agent.evaluation.replay import RecoveryEvalCase
from mobiflow_agent.evaluation.replay import ReplayEvalService

class RecoveryBenchmarkService:
    def __init__(self) -> None:
        self._replay_eval_service = ReplayEvalService()

    def build_case(
        self,
        *,
        source: str,
        eval_case: RecoveryEvalCase,
        memory_case: RecoveryMemoryCase | None = None,
    ) -> RecoveryBenchmarkCase:
        return RecoveryBenchmarkCase(
            benchmark_case_id=build_benchmark_case_id(),
            source=source,
            category=eval_case.category,
            eval_case=eval_case,
            memory_case=memory_case,
        )

    def build_suite(
        self,
        *,
        name: str,
        cases: list[RecoveryBenchmarkCase],
    ) -> RecoveryBenchmarkSuite:
        return RecoveryBenchmarkSuite(
            suite_id=build_benchmark_suite_id(),
            name=name,
            cases=cases,
        )

    def run_suite(self, suite: RecoveryBenchmarkSuite) -> RecoveryBenchmarkReport:
        results: list[RecoveryBenchmarkCaseResult] = []
        matched_cases = 0

        for benchmark_case in suite.cases:
            eval_result = self._replay_eval_service.evaluate(benchmark_case.eval_case)
            if eval_result.matched:
                matched_cases += 1
            results.append(
                RecoveryBenchmarkCaseResult(
                    benchmark_case_id=benchmark_case.benchmark_case_id,
                    case_id=benchmark_case.eval_case.case_id,
                    matched=eval_result.matched,
                    actual_decision=eval_result.actual_decision,
                    actual_verdict_status=eval_result.actual_verdict_status,
                    summary=eval_result.summary,
                )
            )

        total_cases = len(results)
        mismatched_cases = total_cases - matched_cases
        match_rate = (matched_cases / total_cases) if total_cases else 0.0
        summary = (
            f"Benchmark suite {suite.name} completed: "
            f"{matched_cases}/{total_cases} matched, {mismatched_cases} mismatched."
        )
        return RecoveryBenchmarkReport(
            suite_id=suite.suite_id,
            suite_name=suite.name,
            total_cases=total_cases,
            matched_cases=matched_cases,
            mismatched_cases=mismatched_cases,
            match_rate=match_rate,
            results=results,
            summary=summary,
        )
