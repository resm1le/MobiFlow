from __future__ import annotations

from pathlib import Path

from tests.artifacts import artifact_dir
from uuid import uuid4

from mobiflow_agent.common.contracts import VerificationStatus
from mobiflow_agent.evaluation.benchmark.suite import (
    RecoveryBenchmarkCaseResult,
    RecoveryBenchmarkReport,
)
from mobiflow_agent.evaluation.benchmark.dataset import RecoveryBenchmarkDatasetResult
from mobiflow_agent.evaluation.benchmark.run_report import (
    RecoveryBenchmarkDatasetRunReportPersistenceService,
)
from mobiflow_agent.evaluation.benchmark.run_report import RecoveryBenchmarkDatasetRunReport
from mobiflow_agent.evaluation.benchmark.comparison import (
    RecoveryBenchmarkCaseDeltaStatus,
    RecoveryBenchmarkComparisonStatus,
    RecoveryBenchmarkDatasetRunReportComparison,
    RecoveryBenchmarkRunReportCatalogComparison,
    RecoveryBenchmarkRunReportComparisonSchemaVersion,
)
from mobiflow_agent.evaluation.benchmark.comparison import (
    RecoveryBenchmarkRunReportComparisonService,
)
from mobiflow_agent.execution.followup.driver import RecoveryFollowupDriverDecision


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
        summary=f"{benchmark_case_id}/{case_id} {'matched' if matched else 'mismatched'}",
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


def _test_dir(artifact_tmp_path: Path, name: str) -> Path:
    return artifact_dir(artifact_tmp_path, name)


def test_compare_reports_returns_unchanged_for_identical_reports() -> None:
    service = RecoveryBenchmarkRunReportComparisonService()
    report = _report(cases=[_case_result("bc-1", "case-1", matched=True)])

    comparison = service.compare_reports(baseline=report, candidate=report)

    assert comparison.status == RecoveryBenchmarkComparisonStatus.UNCHANGED
    assert comparison.match_rate_delta == 0
    assert comparison.case_deltas[0].status == RecoveryBenchmarkCaseDeltaStatus.UNCHANGED_PASSING


def test_compare_reports_returns_improved_when_match_rate_increases_without_new_failures() -> None:
    service = RecoveryBenchmarkRunReportComparisonService()
    baseline = _report(
        cases=[
            _case_result("bc-1", "case-1", matched=True),
            _case_result("bc-2", "case-2", matched=False),
        ]
    )
    candidate = _report(
        cases=[
            _case_result("bc-1", "case-1", matched=True),
            _case_result("bc-2", "case-2", matched=True),
        ]
    )

    comparison = service.compare_reports(baseline=baseline, candidate=candidate)

    assert comparison.status == RecoveryBenchmarkComparisonStatus.IMPROVED
    assert comparison.match_rate_delta > 0
    assert RecoveryBenchmarkCaseDeltaStatus.NEWLY_PASSING in {item.status for item in comparison.case_deltas}


def test_compare_reports_returns_regressed_when_candidate_has_newly_failing_case() -> None:
    service = RecoveryBenchmarkRunReportComparisonService()
    baseline = _report(cases=[_case_result("bc-1", "case-1", matched=True)])
    candidate = _report(cases=[_case_result("bc-1", "case-1", matched=False)])

    comparison = service.compare_reports(baseline=baseline, candidate=candidate)

    assert comparison.status == RecoveryBenchmarkComparisonStatus.REGRESSED
    assert comparison.case_deltas[0].status == RecoveryBenchmarkCaseDeltaStatus.NEWLY_FAILING


def test_compare_reports_returns_mixed_when_case_set_changes_without_rate_change() -> None:
    service = RecoveryBenchmarkRunReportComparisonService()
    baseline = _report(
        cases=[
            _case_result("bc-1", "case-1", matched=True),
            _case_result("bc-removed", "case-removed", matched=False),
        ]
    )
    candidate = _report(
        cases=[
            _case_result("bc-1", "case-1", matched=True),
            _case_result("bc-added", "case-added", matched=False),
        ]
    )

    comparison = service.compare_reports(baseline=baseline, candidate=candidate)

    assert comparison.status == RecoveryBenchmarkComparisonStatus.MIXED
    assert {item.status for item in comparison.case_deltas} == {
        RecoveryBenchmarkCaseDeltaStatus.ADDED,
        RecoveryBenchmarkCaseDeltaStatus.REMOVED,
        RecoveryBenchmarkCaseDeltaStatus.UNCHANGED_PASSING,
    }


def test_compare_reports_returns_incompatible_for_different_dataset_ids() -> None:
    service = RecoveryBenchmarkRunReportComparisonService()
    baseline = _report(dataset_id="benchmark-dataset:base", cases=[_case_result("bc-1", "case-1", matched=True)])
    candidate = _report(dataset_id="benchmark-dataset:candidate", cases=[_case_result("bc-1", "case-1", matched=True)])

    comparison = service.compare_reports(baseline=baseline, candidate=candidate)

    assert comparison.status == RecoveryBenchmarkComparisonStatus.INCOMPATIBLE
    assert comparison.case_deltas == []


def test_case_delta_classifies_all_supported_statuses() -> None:
    service = RecoveryBenchmarkRunReportComparisonService()
    baseline = _report(
        cases=[
            _case_result("bc-added-base", "case-added-base", matched=True),
            _case_result("bc-failing", "case-failing", matched=True),
            _case_result("bc-passing", "case-passing", matched=False),
            _case_result("bc-same-fail", "case-same-fail", matched=False),
            _case_result("bc-same-pass", "case-same-pass", matched=True),
        ]
    )
    candidate = _report(
        cases=[
            _case_result("bc-added-candidate", "case-added-candidate", matched=True),
            _case_result("bc-failing", "case-failing", matched=False),
            _case_result("bc-passing", "case-passing", matched=True),
            _case_result("bc-same-fail", "case-same-fail", matched=False),
            _case_result("bc-same-pass", "case-same-pass", matched=True),
        ]
    )

    comparison = service.compare_reports(baseline=baseline, candidate=candidate)
    statuses = {item.status for item in comparison.case_deltas}

    assert statuses == {
        RecoveryBenchmarkCaseDeltaStatus.ADDED,
        RecoveryBenchmarkCaseDeltaStatus.REMOVED,
        RecoveryBenchmarkCaseDeltaStatus.NEWLY_FAILING,
        RecoveryBenchmarkCaseDeltaStatus.NEWLY_PASSING,
        RecoveryBenchmarkCaseDeltaStatus.UNCHANGED_FAILING,
        RecoveryBenchmarkCaseDeltaStatus.UNCHANGED_PASSING,
    }


def test_compare_report_files_loads_persisted_reports(artifact_tmp_path) -> None:
    persistence = RecoveryBenchmarkDatasetRunReportPersistenceService()
    service = RecoveryBenchmarkRunReportComparisonService()
    tmp_path = _test_dir(artifact_tmp_path, "files")
    baseline = _report(cases=[_case_result("bc-1", "case-1", matched=False)])
    candidate = _report(cases=[_case_result("bc-1", "case-1", matched=True)])
    baseline_path = tmp_path / "baseline.json"
    candidate_path = tmp_path / "candidate.json"
    persistence.save_report(report=baseline, output_path=str(baseline_path))
    persistence.save_report(report=candidate, output_path=str(candidate_path))

    comparison = service.compare_report_files(
        baseline_path=str(baseline_path),
        candidate_path=str(candidate_path),
    )

    assert comparison.status == RecoveryBenchmarkComparisonStatus.IMPROVED


def test_compare_catalog_dataset_loads_named_dataset_from_both_catalogs(artifact_tmp_path) -> None:
    persistence = RecoveryBenchmarkDatasetRunReportPersistenceService()
    service = RecoveryBenchmarkRunReportComparisonService()
    tmp_path = _test_dir(artifact_tmp_path, "catalog-dataset")
    baseline_dir = tmp_path / "baseline"
    candidate_dir = tmp_path / "candidate"
    baseline = _report(cases=[_case_result("bc-1", "case-1", matched=False)])
    candidate = _report(cases=[_case_result("bc-1", "case-1", matched=True)])
    persistence.save_to_catalog(report=baseline, catalog_dir=str(baseline_dir))
    persistence.save_to_catalog(report=candidate, catalog_dir=str(candidate_dir))

    comparison = service.compare_catalog_dataset(
        baseline_catalog_dir=str(baseline_dir),
        candidate_catalog_dir=str(candidate_dir),
        dataset_id=baseline.dataset_id,
    )

    assert comparison.status == RecoveryBenchmarkComparisonStatus.IMPROVED


def test_compare_catalogs_outputs_sorted_comparisons_and_missing_dataset_ids(artifact_tmp_path) -> None:
    persistence = RecoveryBenchmarkDatasetRunReportPersistenceService()
    service = RecoveryBenchmarkRunReportComparisonService()
    tmp_path = _test_dir(artifact_tmp_path, "catalogs")
    baseline_dir = tmp_path / "baseline"
    candidate_dir = tmp_path / "candidate"
    baseline_a = _report(dataset_id="benchmark-dataset:a", cases=[_case_result("bc-1", "case-1", matched=True)])
    candidate_a = _report(dataset_id="benchmark-dataset:a", cases=[_case_result("bc-1", "case-1", matched=True)])
    baseline_b = _report(dataset_id="benchmark-dataset:b", cases=[_case_result("bc-2", "case-2", matched=True)])
    candidate_b = _report(dataset_id="benchmark-dataset:b", cases=[_case_result("bc-2", "case-2", matched=False)])
    baseline_only = _report(dataset_id="benchmark-dataset:baseline-only", cases=[_case_result("bc-3", "case-3", matched=True)])
    candidate_only = _report(dataset_id="benchmark-dataset:candidate-only", cases=[_case_result("bc-4", "case-4", matched=True)])
    persistence.save_to_catalog(report=baseline_b, catalog_dir=str(baseline_dir))
    persistence.save_to_catalog(report=baseline_a, catalog_dir=str(baseline_dir))
    persistence.save_to_catalog(report=baseline_only, catalog_dir=str(baseline_dir))
    persistence.save_to_catalog(report=candidate_b, catalog_dir=str(candidate_dir))
    persistence.save_to_catalog(report=candidate_a, catalog_dir=str(candidate_dir))
    persistence.save_to_catalog(report=candidate_only, catalog_dir=str(candidate_dir))

    comparison = service.compare_catalogs(
        baseline_catalog_dir=str(baseline_dir),
        candidate_catalog_dir=str(candidate_dir),
    )

    assert [item.baseline_dataset_id for item in comparison.comparisons] == [
        "benchmark-dataset:a",
        "benchmark-dataset:b",
    ]
    assert comparison.compared_datasets == 2
    assert comparison.unchanged_datasets == 1
    assert comparison.regressed_datasets == 1
    assert comparison.missing_baseline_dataset_ids == ["benchmark-dataset:candidate-only"]
    assert comparison.missing_candidate_dataset_ids == ["benchmark-dataset:baseline-only"]


def test_comparison_assets_support_roundtrip() -> None:
    service = RecoveryBenchmarkRunReportComparisonService()
    baseline = _report(cases=[_case_result("bc-1", "case-1", matched=True)])
    candidate = _report(cases=[_case_result("bc-1", "case-1", matched=True)])
    comparison = service.compare_reports(baseline=baseline, candidate=candidate)
    catalog_comparison = RecoveryBenchmarkRunReportCatalogComparison(
        baseline_catalog_dir="baseline",
        candidate_catalog_dir="candidate",
        compared_datasets=1,
        improved_datasets=0,
        regressed_datasets=0,
        unchanged_datasets=1,
        mixed_datasets=0,
        incompatible_datasets=0,
        missing_baseline_dataset_ids=[],
        missing_candidate_dataset_ids=[],
        comparisons=[comparison],
        summary="catalog comparison summary",
    )

    restored_comparison = RecoveryBenchmarkDatasetRunReportComparison.model_validate(
        comparison.model_dump(mode="python")
    )
    restored_catalog = RecoveryBenchmarkRunReportCatalogComparison.model_validate(
        catalog_comparison.model_dump(mode="python")
    )

    assert restored_comparison.schema_version == RecoveryBenchmarkRunReportComparisonSchemaVersion.V1
    assert restored_catalog.schema_version == RecoveryBenchmarkRunReportComparisonSchemaVersion.V1
    assert restored_catalog.comparisons[0].status == RecoveryBenchmarkComparisonStatus.UNCHANGED


def test_comparison_layer_is_static_and_does_not_rerun_benchmark_runner() -> None:
    service = RecoveryBenchmarkRunReportComparisonService()
    baseline = _report(cases=[_case_result("bc-1", "case-1", matched=False)])
    candidate = _report(cases=[_case_result("bc-1", "case-1", matched=True)])

    comparison = service.compare_reports(baseline=baseline, candidate=candidate)

    assert comparison.status == RecoveryBenchmarkComparisonStatus.IMPROVED
    assert comparison.candidate_matched_cases == 1
    assert comparison.baseline_mismatched_cases == 1


