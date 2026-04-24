from __future__ import annotations

"""Benchmark quality gate assets and service."""

from enum import Enum

from pydantic import Field

from mobiflow_agent.common.contracts import StrictModel
from mobiflow_agent.evaluation.benchmark.comparison import RecoveryBenchmarkComparisonKind

class RecoveryBenchmarkQualityGateSchemaVersion(str, Enum):
    V1 = "v1"

class RecoveryBenchmarkQualityGateDecision(str, Enum):
    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"

class RecoveryBenchmarkQualityGatePolicy(StrictModel):
    schema_version: RecoveryBenchmarkQualityGateSchemaVersion = (
        RecoveryBenchmarkQualityGateSchemaVersion.V1
    )
    fail_on_mixed: bool = False

class RecoveryBenchmarkQualityGateViolation(StrictModel):
    violation_id: str = Field(min_length=1)
    comparison_id: str = Field(min_length=1)
    comparison_kind: RecoveryBenchmarkComparisonKind
    decision: RecoveryBenchmarkQualityGateDecision
    reason: str = Field(min_length=1)
    summary: str = Field(min_length=1)

class RecoveryBenchmarkQualityGateResult(StrictModel):
    schema_version: RecoveryBenchmarkQualityGateSchemaVersion = (
        RecoveryBenchmarkQualityGateSchemaVersion.V1
    )
    decision: RecoveryBenchmarkQualityGateDecision
    policy: RecoveryBenchmarkQualityGatePolicy
    evaluated_comparisons: int = Field(ge=0)
    passed_comparisons: int = Field(ge=0)
    warning_comparisons: int = Field(ge=0)
    failed_comparisons: int = Field(ge=0)
    violations: list[RecoveryBenchmarkQualityGateViolation] = Field(default_factory=list)
    summary: str = Field(min_length=1)

from pathlib import Path

from mobiflow_agent.evaluation.benchmark.comparison import RecoveryBenchmarkComparisonKind
from mobiflow_agent.evaluation.benchmark.comparison import (
    RecoveryBenchmarkComparisonPersistenceService,
)
from mobiflow_agent.evaluation.benchmark.comparison import (
    RecoveryBenchmarkComparisonStatus,
    RecoveryBenchmarkDatasetRunReportComparison,
    RecoveryBenchmarkRunReportCatalogComparison,
)

class RecoveryBenchmarkQualityGateService:
    def __init__(
        self,
        persistence_service: RecoveryBenchmarkComparisonPersistenceService | None = None,
    ) -> None:
        self._persistence_service = persistence_service or RecoveryBenchmarkComparisonPersistenceService()

    def evaluate_dataset_comparison(
        self,
        comparison: RecoveryBenchmarkDatasetRunReportComparison,
        *,
        policy: RecoveryBenchmarkQualityGatePolicy | None = None,
    ) -> RecoveryBenchmarkQualityGateResult:
        resolved_policy = policy or RecoveryBenchmarkQualityGatePolicy()
        comparison_id = self._dataset_comparison_id(comparison)
        decision = self._decision_for_status(comparison.status, policy=resolved_policy)
        violations = self._violations_for_status(
            comparison_id=comparison_id,
            comparison_kind=RecoveryBenchmarkComparisonKind.DATASET,
            status=comparison.status,
            decision=decision,
            summary=comparison.summary,
        )
        return self._single_result(
            decision=decision,
            policy=resolved_policy,
            violations=violations,
            summary=(
                f"Benchmark dataset comparison quality gate {decision.value}: "
                f"{comparison.baseline_dataset_id} -> {comparison.candidate_dataset_id}."
            ),
        )

    def evaluate_catalog_comparison(
        self,
        comparison: RecoveryBenchmarkRunReportCatalogComparison,
        *,
        policy: RecoveryBenchmarkQualityGatePolicy | None = None,
    ) -> RecoveryBenchmarkQualityGateResult:
        resolved_policy = policy or RecoveryBenchmarkQualityGatePolicy()
        comparison_id = self._catalog_comparison_id(comparison)
        violations: list[RecoveryBenchmarkQualityGateViolation] = []
        if comparison.regressed_datasets > 0:
            violations.append(
                self._violation(
                    comparison_id=comparison_id,
                    comparison_kind=RecoveryBenchmarkComparisonKind.CATALOG,
                    decision=RecoveryBenchmarkQualityGateDecision.FAILED,
                    reason="regressed_datasets",
                    summary=(
                        f"Catalog comparison has {comparison.regressed_datasets} "
                        "regressed datasets."
                    ),
                )
            )
        if comparison.incompatible_datasets > 0:
            violations.append(
                self._violation(
                    comparison_id=comparison_id,
                    comparison_kind=RecoveryBenchmarkComparisonKind.CATALOG,
                    decision=RecoveryBenchmarkQualityGateDecision.FAILED,
                    reason="incompatible_datasets",
                    summary=(
                        f"Catalog comparison has {comparison.incompatible_datasets} "
                        "incompatible datasets."
                    ),
                )
            )
        if comparison.mixed_datasets > 0:
            mixed_decision = (
                RecoveryBenchmarkQualityGateDecision.FAILED
                if resolved_policy.fail_on_mixed
                else RecoveryBenchmarkQualityGateDecision.WARNING
            )
            violations.append(
                self._violation(
                    comparison_id=comparison_id,
                    comparison_kind=RecoveryBenchmarkComparisonKind.CATALOG,
                    decision=mixed_decision,
                    reason="mixed_datasets",
                    summary=f"Catalog comparison has {comparison.mixed_datasets} mixed datasets.",
                )
            )

        decision = self._aggregate_decision([item.decision for item in violations])
        return self._single_result(
            decision=decision,
            policy=resolved_policy,
            violations=violations,
            summary=(
                f"Benchmark catalog comparison quality gate {decision.value}: "
                f"{comparison.compared_datasets} shared datasets evaluated."
            ),
        )

    def evaluate_comparison_catalog(
        self,
        catalog_dir: str,
        *,
        policy: RecoveryBenchmarkQualityGatePolicy | None = None,
    ) -> RecoveryBenchmarkQualityGateResult:
        resolved_policy = policy or RecoveryBenchmarkQualityGatePolicy()
        catalog = self._persistence_service.list_catalog(catalog_dir)
        if not catalog.entries:
            violation = self._violation(
                comparison_id=f"catalog:{catalog.catalog_dir}",
                comparison_kind=RecoveryBenchmarkComparisonKind.CATALOG,
                decision=RecoveryBenchmarkQualityGateDecision.FAILED,
                reason="no_comparison_evidence",
                summary="Comparison catalog has no comparison documents to evaluate.",
            )
            return RecoveryBenchmarkQualityGateResult(
                decision=RecoveryBenchmarkQualityGateDecision.FAILED,
                policy=resolved_policy,
                evaluated_comparisons=0,
                passed_comparisons=0,
                warning_comparisons=0,
                failed_comparisons=0,
                violations=[violation],
                summary=f"Benchmark comparison catalog quality gate failed: {catalog.catalog_dir} has no evidence.",
            )

        results: list[RecoveryBenchmarkQualityGateResult] = []
        for entry in catalog.entries:
            if entry.comparison_kind == RecoveryBenchmarkComparisonKind.DATASET:
                comparison = self._persistence_service.load_dataset_comparison(entry.path)
                results.append(
                    self.evaluate_dataset_comparison(comparison, policy=resolved_policy)
                )
            else:
                comparison = self._persistence_service.load_catalog_comparison(entry.path)
                results.append(
                    self.evaluate_catalog_comparison(comparison, policy=resolved_policy)
                )

        decision = self._aggregate_decision([item.decision for item in results])
        violations = [
            violation
            for result in results
            for violation in result.violations
        ]
        return RecoveryBenchmarkQualityGateResult(
            decision=decision,
            policy=resolved_policy,
            evaluated_comparisons=len(results),
            passed_comparisons=sum(
                1 for item in results if item.decision == RecoveryBenchmarkQualityGateDecision.PASSED
            ),
            warning_comparisons=sum(
                1 for item in results if item.decision == RecoveryBenchmarkQualityGateDecision.WARNING
            ),
            failed_comparisons=sum(
                1 for item in results if item.decision == RecoveryBenchmarkQualityGateDecision.FAILED
            ),
            violations=violations,
            summary=(
                f"Benchmark comparison catalog quality gate {decision.value}: "
                f"{len(results)} comparisons evaluated."
            ),
        )

    @staticmethod
    def _decision_for_status(
        status: RecoveryBenchmarkComparisonStatus,
        *,
        policy: RecoveryBenchmarkQualityGatePolicy,
    ) -> RecoveryBenchmarkQualityGateDecision:
        if status in {
            RecoveryBenchmarkComparisonStatus.IMPROVED,
            RecoveryBenchmarkComparisonStatus.UNCHANGED,
        }:
            return RecoveryBenchmarkQualityGateDecision.PASSED
        if status == RecoveryBenchmarkComparisonStatus.MIXED:
            if policy.fail_on_mixed:
                return RecoveryBenchmarkQualityGateDecision.FAILED
            return RecoveryBenchmarkQualityGateDecision.WARNING
        return RecoveryBenchmarkQualityGateDecision.FAILED

    @classmethod
    def _violations_for_status(
        cls,
        *,
        comparison_id: str,
        comparison_kind: RecoveryBenchmarkComparisonKind,
        status: RecoveryBenchmarkComparisonStatus,
        decision: RecoveryBenchmarkQualityGateDecision,
        summary: str,
    ) -> list[RecoveryBenchmarkQualityGateViolation]:
        if decision == RecoveryBenchmarkQualityGateDecision.PASSED:
            return []
        return [
            cls._violation(
                comparison_id=comparison_id,
                comparison_kind=comparison_kind,
                decision=decision,
                reason=f"comparison_status_{status.value}",
                summary=summary,
            )
        ]

    @staticmethod
    def _single_result(
        *,
        decision: RecoveryBenchmarkQualityGateDecision,
        policy: RecoveryBenchmarkQualityGatePolicy,
        violations: list[RecoveryBenchmarkQualityGateViolation],
        summary: str,
    ) -> RecoveryBenchmarkQualityGateResult:
        return RecoveryBenchmarkQualityGateResult(
            decision=decision,
            policy=policy,
            evaluated_comparisons=1,
            passed_comparisons=1 if decision == RecoveryBenchmarkQualityGateDecision.PASSED else 0,
            warning_comparisons=1 if decision == RecoveryBenchmarkQualityGateDecision.WARNING else 0,
            failed_comparisons=1 if decision == RecoveryBenchmarkQualityGateDecision.FAILED else 0,
            violations=violations,
            summary=summary,
        )

    @staticmethod
    def _aggregate_decision(
        decisions: list[RecoveryBenchmarkQualityGateDecision],
    ) -> RecoveryBenchmarkQualityGateDecision:
        if RecoveryBenchmarkQualityGateDecision.FAILED in decisions:
            return RecoveryBenchmarkQualityGateDecision.FAILED
        if RecoveryBenchmarkQualityGateDecision.WARNING in decisions:
            return RecoveryBenchmarkQualityGateDecision.WARNING
        return RecoveryBenchmarkQualityGateDecision.PASSED

    @staticmethod
    def _dataset_comparison_id(comparison: RecoveryBenchmarkDatasetRunReportComparison) -> str:
        return f"dataset:{comparison.baseline_dataset_id}:{comparison.candidate_dataset_id}"

    @staticmethod
    def _catalog_comparison_id(comparison: RecoveryBenchmarkRunReportCatalogComparison) -> str:
        baseline_id = RecoveryBenchmarkQualityGateService._safe_path_id(
            comparison.baseline_catalog_dir
        )
        candidate_id = RecoveryBenchmarkQualityGateService._safe_path_id(
            comparison.candidate_catalog_dir
        )
        return f"catalog:{baseline_id}:{candidate_id}"

    @staticmethod
    def _safe_path_id(path: str) -> str:
        return str(Path(path).resolve()).replace("\\", "/").replace("/", "__")

    @staticmethod
    def _violation(
        *,
        comparison_id: str,
        comparison_kind: RecoveryBenchmarkComparisonKind,
        decision: RecoveryBenchmarkQualityGateDecision,
        reason: str,
        summary: str,
    ) -> RecoveryBenchmarkQualityGateViolation:
        return RecoveryBenchmarkQualityGateViolation(
            violation_id=f"{comparison_id}:{reason}",
            comparison_id=comparison_id,
            comparison_kind=comparison_kind,
            decision=decision,
            reason=reason,
            summary=summary,
        )
