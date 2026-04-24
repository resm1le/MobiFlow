from __future__ import annotations

"""Benchmark dataset assets and service."""

from enum import Enum
from uuid import uuid4

from pydantic import Field, model_validator

from mobiflow_agent.common.contracts import StrictModel
from mobiflow_agent.evaluation.benchmark.suite import RecoveryBenchmarkReport, RecoveryBenchmarkSuite

class RecoveryBenchmarkDatasetSchemaVersion(str, Enum):
    V1 = "v1"

class RecoveryBenchmarkDataset(StrictModel):
    schema_version: RecoveryBenchmarkDatasetSchemaVersion = RecoveryBenchmarkDatasetSchemaVersion.V1
    dataset_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    source: str = Field(min_length=1)
    suites: list[RecoveryBenchmarkSuite] = Field(default_factory=list)
    summary: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_suites(self) -> "RecoveryBenchmarkDataset":
        if not self.suites:
            raise ValueError("RecoveryBenchmarkDataset requires at least one suite.")
        return self

class RecoveryBenchmarkDatasetResult(StrictModel):
    schema_version: RecoveryBenchmarkDatasetSchemaVersion = RecoveryBenchmarkDatasetSchemaVersion.V1
    dataset_id: str = Field(min_length=1)
    dataset_name: str = Field(min_length=1)
    total_suites: int = Field(ge=0)
    total_cases: int = Field(ge=0)
    matched_cases: int = Field(ge=0)
    mismatched_cases: int = Field(ge=0)
    match_rate: float = Field(ge=0.0, le=1.0)
    suite_reports: list[RecoveryBenchmarkReport] = Field(default_factory=list)
    summary: str = Field(min_length=1)

def build_benchmark_dataset_id() -> str:
    return f"benchmark-dataset:{uuid4().hex}"

from mobiflow_agent.evaluation.benchmark.suite import RecoveryBenchmarkSuite
from mobiflow_agent.evaluation.benchmark.suite import RecoveryBenchmarkService

class RecoveryBenchmarkDatasetService:
    def __init__(self) -> None:
        self._benchmark_service = RecoveryBenchmarkService()

    def build_dataset(
        self,
        *,
        name: str,
        source: str,
        suites: list[RecoveryBenchmarkSuite],
    ) -> RecoveryBenchmarkDataset:
        total_cases = sum(len(suite.cases) for suite in suites)
        summary = (
            f"Benchmark dataset {name} contains "
            f"{len(suites)} suites and {total_cases} cases."
        )
        return RecoveryBenchmarkDataset(
            dataset_id=build_benchmark_dataset_id(),
            name=name,
            source=source,
            suites=suites,
            summary=summary,
        )

    def run_dataset(self, dataset: RecoveryBenchmarkDataset) -> RecoveryBenchmarkDatasetResult:
        suite_reports = [self._benchmark_service.run_suite(suite) for suite in dataset.suites]
        total_suites = len(suite_reports)
        total_cases = sum(report.total_cases for report in suite_reports)
        matched_cases = sum(report.matched_cases for report in suite_reports)
        mismatched_cases = sum(report.mismatched_cases for report in suite_reports)
        match_rate = (matched_cases / total_cases) if total_cases else 0.0
        summary = (
            f"Benchmark dataset {dataset.name} completed: "
            f"{total_suites} suites, {total_cases} cases, "
            f"{matched_cases} matched, {mismatched_cases} mismatched."
        )
        return RecoveryBenchmarkDatasetResult(
            dataset_id=dataset.dataset_id,
            dataset_name=dataset.name,
            total_suites=total_suites,
            total_cases=total_cases,
            matched_cases=matched_cases,
            mismatched_cases=mismatched_cases,
            match_rate=match_rate,
            suite_reports=suite_reports,
            summary=summary,
        )
