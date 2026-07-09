from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from tests.artifacts import artifact_dir

from mobiflow_agent.common.contracts import VerificationStatus
from mobiflow_agent.evaluation.benchmark.suite import (
    RecoveryBenchmarkCaseResult,
    RecoveryBenchmarkReport,
)
from mobiflow_agent.evaluation.benchmark.comparison import (
    RecoveryBenchmarkComparisonPersistenceService,
)
from mobiflow_agent.evaluation.benchmark.dataset import RecoveryBenchmarkDatasetResult
from mobiflow_agent.evaluation.benchmark.run_report import RecoveryBenchmarkDatasetRunReport
from mobiflow_agent.evaluation.benchmark.quality_gate import (
    RecoveryBenchmarkQualityGateDecision,
    RecoveryBenchmarkQualityGatePolicy,
    RecoveryBenchmarkQualityGateResult,
    RecoveryBenchmarkQualityGateSchemaVersion,
)
from mobiflow_agent.evaluation.benchmark.quality_gate import (
    RecoveryBenchmarkQualityGateService,
)
from mobiflow_agent.evaluation.benchmark.comparison import (
    RecoveryBenchmarkComparisonStatus,
    RecoveryBenchmarkRunReportCatalogComparison,
)
from mobiflow_agent.evaluation.benchmark.comparison import (
    RecoveryBenchmarkRunReportComparisonService,
)
from mobiflow_agent.execution.followup.decisions import RecoveryFollowupDriverDecision


def _case_result(
    benchmark_case_id: str,
    case_id: str,
    *,
    matched: bool,
) -> RecoveryBenchmarkCaseResult:
    return RecoveryBenchmarkCaseResult(
        benchmark_case_id=benchmark_case_id,
        case_id=case_id,
        matched=matched,
        actual_decision=RecoveryFollowupDriverDecision.COMPLETE,
        actual_verdict_status=VerificationStatus.VERIFIED_SUCCESS,
        summary=f"{benchmark_case_id}/{case_id}",
    )


def _report(
    *,
    dataset_id: str = "benchmark-dataset:alpha",
    dataset_name: str = "dataset-alpha",
    cases: list[RecoveryBenchmarkCaseResult],
) -> RecoveryBenchmarkDatasetRunReport:
    matched_cases = sum(1 for case in cases if case.matched)
    mismatched_cases = len(cases) - matched_cases
    match_rate = matched_cases / len(cases) if cases else 0.0
    suite_report = RecoveryBenchmarkReport(
        suite_id="suite-alpha",
        suite_name="suite-alpha",
        total_cases=len(cases),
        matched_cases=matched_cases,
        mismatched_cases=mismatched_cases,
        match_rate=match_rate,
        results=cases,
        summary="suite summary",
    )
    result = RecoveryBenchmarkDatasetResult(
        dataset_id=dataset_id,
        dataset_name=dataset_name,
        total_suites=1,
        total_cases=len(cases),
        matched_cases=matched_cases,
        mismatched_cases=mismatched_cases,
        match_rate=match_rate,
        suite_reports=[suite_report],
        summary="dataset result summary",
    )
    return RecoveryBenchmarkDatasetRunReport(
        dataset_id=dataset_id,
        dataset_name=dataset_name,
        source_path=None,
        result=result,
        summary="dataset run report summary",
    )


def _dataset_comparison(
    *,
    dataset_id: str = "benchmark-dataset:alpha",
    baseline_cases: list[RecoveryBenchmarkCaseResult],
    candidate_cases: list[RecoveryBenchmarkCaseResult],
):
    baseline = _report(dataset_id=dataset_id, cases=baseline_cases)
    candidate = _report(dataset_id=dataset_id, cases=candidate_cases)
    return RecoveryBenchmarkRunReportComparisonService().compare_reports(
        baseline=baseline,
        candidate=candidate,
    )


def _catalog_comparison(
    *,
    regressed: int = 0,
    incompatible: int = 0,
    mixed: int = 0,
    improved: int = 0,
    unchanged: int = 0,
) -> RecoveryBenchmarkRunReportCatalogComparison:
    return RecoveryBenchmarkRunReportCatalogComparison(
        baseline_catalog_dir="baseline",
        candidate_catalog_dir="candidate",
        compared_datasets=regressed + incompatible + mixed + improved + unchanged,
        improved_datasets=improved,
        regressed_datasets=regressed,
        unchanged_datasets=unchanged,
        mixed_datasets=mixed,
        incompatible_datasets=incompatible,
        missing_baseline_dataset_ids=[],
        missing_candidate_dataset_ids=[],
        comparisons=[],
        summary="catalog comparison summary",
    )


def _test_dir(artifact_tmp_path: Path, name: str) -> Path:
    return artifact_dir(artifact_tmp_path, name)


def test_dataset_comparison_improved_and_unchanged_pass() -> None:
    service = RecoveryBenchmarkQualityGateService()
    improved = _dataset_comparison(
        baseline_cases=[_case_result("bc-1", "case-1", matched=False)],
        candidate_cases=[_case_result("bc-1", "case-1", matched=True)],
    )
    unchanged = _dataset_comparison(
        baseline_cases=[_case_result("bc-1", "case-1", matched=True)],
        candidate_cases=[_case_result("bc-1", "case-1", matched=True)],
    )

    improved_result = service.evaluate_dataset_comparison(improved)
    unchanged_result = service.evaluate_dataset_comparison(unchanged)

    assert improved.status == RecoveryBenchmarkComparisonStatus.IMPROVED
    assert improved_result.decision == RecoveryBenchmarkQualityGateDecision.PASSED
    assert unchanged.status == RecoveryBenchmarkComparisonStatus.UNCHANGED
    assert unchanged_result.decision == RecoveryBenchmarkQualityGateDecision.PASSED


def test_dataset_comparison_regressed_and_incompatible_fail() -> None:
    service = RecoveryBenchmarkQualityGateService()
    regressed = _dataset_comparison(
        baseline_cases=[_case_result("bc-1", "case-1", matched=True)],
        candidate_cases=[_case_result("bc-1", "case-1", matched=False)],
    )
    incompatible = RecoveryBenchmarkRunReportComparisonService().compare_reports(
        baseline=_report(
            dataset_id="benchmark-dataset:baseline",
            cases=[_case_result("bc-1", "case-1", matched=True)],
        ),
        candidate=_report(
            dataset_id="benchmark-dataset:candidate",
            cases=[_case_result("bc-1", "case-1", matched=True)],
        ),
    )

    regressed_result = service.evaluate_dataset_comparison(regressed)
    incompatible_result = service.evaluate_dataset_comparison(incompatible)

    assert regressed.status == RecoveryBenchmarkComparisonStatus.REGRESSED
    assert regressed_result.decision == RecoveryBenchmarkQualityGateDecision.FAILED
    assert regressed_result.failed_comparisons == 1
    assert incompatible.status == RecoveryBenchmarkComparisonStatus.INCOMPATIBLE
    assert incompatible_result.decision == RecoveryBenchmarkQualityGateDecision.FAILED
    assert incompatible_result.violations[0].reason == "comparison_status_incompatible"


def test_dataset_comparison_mixed_warns_by_default_and_can_fail() -> None:
    service = RecoveryBenchmarkQualityGateService()
    mixed = _dataset_comparison(
        baseline_cases=[
            _case_result("bc-1", "case-1", matched=True),
            _case_result("bc-removed", "case-removed", matched=False),
        ],
        candidate_cases=[
            _case_result("bc-1", "case-1", matched=True),
            _case_result("bc-added", "case-added", matched=False),
        ],
    )

    default_result = service.evaluate_dataset_comparison(mixed)
    strict_result = service.evaluate_dataset_comparison(
        mixed,
        policy=RecoveryBenchmarkQualityGatePolicy(fail_on_mixed=True),
    )

    assert mixed.status == RecoveryBenchmarkComparisonStatus.MIXED
    assert default_result.decision == RecoveryBenchmarkQualityGateDecision.WARNING
    assert strict_result.decision == RecoveryBenchmarkQualityGateDecision.FAILED


def test_catalog_comparison_aggregates_regressed_incompatible_and_mixed() -> None:
    service = RecoveryBenchmarkQualityGateService()
    failed = service.evaluate_catalog_comparison(
        _catalog_comparison(regressed=1, incompatible=1, mixed=1)
    )
    warning = service.evaluate_catalog_comparison(_catalog_comparison(mixed=1))
    strict_mixed = service.evaluate_catalog_comparison(
        _catalog_comparison(mixed=1),
        policy=RecoveryBenchmarkQualityGatePolicy(fail_on_mixed=True),
    )
    passed = service.evaluate_catalog_comparison(_catalog_comparison(improved=1, unchanged=1))

    assert failed.decision == RecoveryBenchmarkQualityGateDecision.FAILED
    assert {item.reason for item in failed.violations} == {
        "regressed_datasets",
        "incompatible_datasets",
        "mixed_datasets",
    }
    assert warning.decision == RecoveryBenchmarkQualityGateDecision.WARNING
    assert strict_mixed.decision == RecoveryBenchmarkQualityGateDecision.FAILED
    assert passed.decision == RecoveryBenchmarkQualityGateDecision.PASSED


def test_comparison_catalog_loads_documents_and_aggregates_results(artifact_tmp_path) -> None:
    persistence = RecoveryBenchmarkComparisonPersistenceService()
    service = RecoveryBenchmarkQualityGateService()
    catalog_dir = _test_dir(artifact_tmp_path, "catalog")
    passed_comparison = _dataset_comparison(
        dataset_id="benchmark-dataset:passed",
        baseline_cases=[_case_result("bc-1", "case-1", matched=False)],
        candidate_cases=[_case_result("bc-1", "case-1", matched=True)],
    )
    warning_comparison = _dataset_comparison(
        dataset_id="benchmark-dataset:warning",
        baseline_cases=[
            _case_result("bc-1", "case-1", matched=True),
            _case_result("bc-removed", "case-removed", matched=False),
        ],
        candidate_cases=[
            _case_result("bc-1", "case-1", matched=True),
            _case_result("bc-added", "case-added", matched=False),
        ],
    )
    failed_catalog_comparison = _catalog_comparison(regressed=1)
    persistence.save_to_catalog(comparison=passed_comparison, catalog_dir=str(catalog_dir))
    persistence.save_to_catalog(comparison=warning_comparison, catalog_dir=str(catalog_dir))
    persistence.save_to_catalog(comparison=failed_catalog_comparison, catalog_dir=str(catalog_dir))

    result = service.evaluate_comparison_catalog(str(catalog_dir))

    assert result.decision == RecoveryBenchmarkQualityGateDecision.FAILED
    assert result.evaluated_comparisons == 3
    assert result.passed_comparisons == 1
    assert result.warning_comparisons == 1
    assert result.failed_comparisons == 1
    assert {item.reason for item in result.violations} == {
        "comparison_status_mixed",
        "regressed_datasets",
    }


def test_empty_comparison_catalog_fails_with_no_evidence_summary(artifact_tmp_path) -> None:
    result = RecoveryBenchmarkQualityGateService().evaluate_comparison_catalog(
        str(_test_dir(artifact_tmp_path, "empty-catalog"))
    )

    assert result.decision == RecoveryBenchmarkQualityGateDecision.FAILED
    assert result.evaluated_comparisons == 0
    assert result.violations[0].reason == "no_comparison_evidence"
    assert "no evidence" in result.summary


def test_quality_gate_assets_support_roundtrip() -> None:
    result = RecoveryBenchmarkQualityGateService().evaluate_catalog_comparison(
        _catalog_comparison(mixed=1)
    )

    restored = RecoveryBenchmarkQualityGateResult.model_validate(result.model_dump(mode="python"))

    assert restored.schema_version == RecoveryBenchmarkQualityGateSchemaVersion.V1
    assert restored.policy.schema_version == RecoveryBenchmarkQualityGateSchemaVersion.V1
    assert restored.decision == RecoveryBenchmarkQualityGateDecision.WARNING


def test_invalid_comparison_document_errors_are_owned_by_persistence_layer(artifact_tmp_path) -> None:
    catalog_dir = _test_dir(artifact_tmp_path, "invalid-document")
    path = catalog_dir / "broken.json"
    path.write_text(json.dumps({"schema_version": "v1", "comparison": {"oops": True}}), encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid benchmark comparison document schema"):
        RecoveryBenchmarkQualityGateService().evaluate_comparison_catalog(str(catalog_dir))


def test_quality_gate_layer_is_static_and_uses_existing_comparison_status() -> None:
    comparison = _dataset_comparison(
        baseline_cases=[_case_result("bc-1", "case-1", matched=True)],
        candidate_cases=[_case_result("bc-1", "case-1", matched=False)],
    )

    result = RecoveryBenchmarkQualityGateService().evaluate_dataset_comparison(comparison)

    assert comparison.status == RecoveryBenchmarkComparisonStatus.REGRESSED
    assert result.decision == RecoveryBenchmarkQualityGateDecision.FAILED
    assert result.summary.startswith("Benchmark dataset comparison quality gate failed")


