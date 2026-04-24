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
from mobiflow_agent.evaluation.benchmark.history import (
    RecoveryBenchmarkComparisonHistory,
    RecoveryBenchmarkComparisonHistoryCatalog,
    RecoveryBenchmarkComparisonHistoryDocument,
    RecoveryBenchmarkComparisonHistorySchemaVersion,
)
from mobiflow_agent.evaluation.benchmark.history import (
    RecoveryBenchmarkComparisonHistoryService,
)
from mobiflow_agent.evaluation.benchmark.comparison import (
    RecoveryBenchmarkComparisonKind,
)
from mobiflow_agent.evaluation.benchmark.comparison import (
    RecoveryBenchmarkComparisonPersistenceService,
)
from mobiflow_agent.evaluation.benchmark.dataset import RecoveryBenchmarkDatasetResult
from mobiflow_agent.evaluation.benchmark.run_report import RecoveryBenchmarkDatasetRunReport
from mobiflow_agent.evaluation.benchmark.quality_gate import (
    RecoveryBenchmarkQualityGateDecision,
    RecoveryBenchmarkQualityGatePolicy,
)
from mobiflow_agent.evaluation.benchmark.comparison import (
    RecoveryBenchmarkComparisonStatus,
    RecoveryBenchmarkRunReportCatalogComparison,
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


def _passed_comparison(dataset_id: str = "benchmark-dataset:passed"):
    return _dataset_comparison(
        dataset_id=dataset_id,
        baseline_cases=[_case_result("bc-1", "case-1", matched=False)],
        candidate_cases=[_case_result("bc-1", "case-1", matched=True)],
    )


def _warning_comparison(dataset_id: str = "benchmark-dataset:warning"):
    return _dataset_comparison(
        dataset_id=dataset_id,
        baseline_cases=[
            _case_result("bc-1", "case-1", matched=True),
            _case_result("bc-removed", "case-removed", matched=False),
        ],
        candidate_cases=[
            _case_result("bc-1", "case-1", matched=True),
            _case_result("bc-added", "case-added", matched=False),
        ],
    )


def _failed_comparison(dataset_id: str = "benchmark-dataset:failed"):
    return _dataset_comparison(
        dataset_id=dataset_id,
        baseline_cases=[_case_result("bc-1", "case-1", matched=True)],
        candidate_cases=[_case_result("bc-1", "case-1", matched=False)],
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


def test_build_history_reads_dataset_and_catalog_comparison_documents(artifact_tmp_path) -> None:
    persistence = RecoveryBenchmarkComparisonPersistenceService()
    service = RecoveryBenchmarkComparisonHistoryService()
    catalog_dir = _test_dir(artifact_tmp_path, "mixed-kind-catalog")
    persistence.save_to_catalog(comparison=_passed_comparison(), catalog_dir=str(catalog_dir))
    persistence.save_to_catalog(
        comparison=_catalog_comparison(regressed=1),
        catalog_dir=str(catalog_dir),
    )

    history = service.build_history(str(catalog_dir), history_id="history:explicit")

    assert history.history_id == "history:explicit"
    assert history.overall_decision == RecoveryBenchmarkQualityGateDecision.FAILED
    assert history.evaluated_comparisons == 2
    assert history.passed_comparisons == 1
    assert history.failed_comparisons == 1
    assert {entry.comparison_kind for entry in history.entries} == {
        RecoveryBenchmarkComparisonKind.DATASET,
        RecoveryBenchmarkComparisonKind.CATALOG,
    }
    assert {entry.gate_decision for entry in history.entries} == {
        RecoveryBenchmarkQualityGateDecision.PASSED,
        RecoveryBenchmarkQualityGateDecision.FAILED,
    }


def test_history_entries_preserve_minimum_comparison_evidence(artifact_tmp_path) -> None:
    persistence = RecoveryBenchmarkComparisonPersistenceService()
    service = RecoveryBenchmarkComparisonHistoryService()
    catalog_dir = _test_dir(artifact_tmp_path, "entry-evidence")
    comparison = _failed_comparison()
    catalog_entry = persistence.save_to_catalog(comparison=comparison, catalog_dir=str(catalog_dir))

    history = service.build_history(str(catalog_dir))
    entry = history.entries[0]

    assert entry.comparison_id == catalog_entry.comparison_id
    assert entry.comparison_kind == RecoveryBenchmarkComparisonKind.DATASET
    assert entry.baseline_id == comparison.baseline_dataset_id
    assert entry.candidate_id == comparison.candidate_dataset_id
    assert entry.status == RecoveryBenchmarkComparisonStatus.REGRESSED
    assert entry.gate_decision == RecoveryBenchmarkQualityGateDecision.FAILED
    assert entry.violation_count == 1
    assert entry.path == catalog_entry.path
    assert entry.summary == comparison.summary


def test_mixed_history_warns_by_default_and_can_fail(artifact_tmp_path) -> None:
    persistence = RecoveryBenchmarkComparisonPersistenceService()
    service = RecoveryBenchmarkComparisonHistoryService()
    catalog_dir = _test_dir(artifact_tmp_path, "mixed-policy")
    persistence.save_to_catalog(comparison=_warning_comparison(), catalog_dir=str(catalog_dir))

    default_history = service.build_history(str(catalog_dir))
    strict_history = service.build_history(
        str(catalog_dir),
        policy=RecoveryBenchmarkQualityGatePolicy(fail_on_mixed=True),
    )

    assert default_history.overall_decision == RecoveryBenchmarkQualityGateDecision.WARNING
    assert default_history.warning_comparisons == 1
    assert strict_history.overall_decision == RecoveryBenchmarkQualityGateDecision.FAILED
    assert strict_history.failed_comparisons == 1


def test_history_aggregates_failed_warning_and_passed_results(artifact_tmp_path) -> None:
    persistence = RecoveryBenchmarkComparisonPersistenceService()
    service = RecoveryBenchmarkComparisonHistoryService()
    failed_dir = _test_dir(artifact_tmp_path, "failed")
    warning_dir = _test_dir(artifact_tmp_path, "warning")
    passed_dir = _test_dir(artifact_tmp_path, "passed")

    persistence.save_to_catalog(comparison=_passed_comparison("benchmark-dataset:a"), catalog_dir=str(failed_dir))
    persistence.save_to_catalog(comparison=_failed_comparison("benchmark-dataset:b"), catalog_dir=str(failed_dir))
    persistence.save_to_catalog(comparison=_passed_comparison("benchmark-dataset:a"), catalog_dir=str(warning_dir))
    persistence.save_to_catalog(comparison=_warning_comparison("benchmark-dataset:b"), catalog_dir=str(warning_dir))
    persistence.save_to_catalog(comparison=_passed_comparison("benchmark-dataset:a"), catalog_dir=str(passed_dir))
    persistence.save_to_catalog(comparison=_passed_comparison("benchmark-dataset:b"), catalog_dir=str(passed_dir))

    failed_history = service.build_history(str(failed_dir))
    warning_history = service.build_history(str(warning_dir))
    passed_history = service.build_history(str(passed_dir))

    assert failed_history.overall_decision == RecoveryBenchmarkQualityGateDecision.FAILED
    assert warning_history.overall_decision == RecoveryBenchmarkQualityGateDecision.WARNING
    assert passed_history.overall_decision == RecoveryBenchmarkQualityGateDecision.PASSED


def test_empty_comparison_catalog_builds_failed_history_with_no_evidence_summary(artifact_tmp_path) -> None:
    history = RecoveryBenchmarkComparisonHistoryService().build_history(str(_test_dir(artifact_tmp_path, "empty")))

    assert history.overall_decision == RecoveryBenchmarkQualityGateDecision.FAILED
    assert history.evaluated_comparisons == 0
    assert history.entries == []
    assert history.violations[0].reason == "no_comparison_evidence"
    assert "no comparison evidence" in history.summary


def test_history_assets_and_document_support_roundtrip(artifact_tmp_path) -> None:
    persistence = RecoveryBenchmarkComparisonPersistenceService()
    catalog_dir = _test_dir(artifact_tmp_path, "roundtrip")
    persistence.save_to_catalog(comparison=_warning_comparison(), catalog_dir=str(catalog_dir))
    history = RecoveryBenchmarkComparisonHistoryService().build_history(str(catalog_dir))
    document = RecoveryBenchmarkComparisonHistoryDocument(history=history)

    restored_history = RecoveryBenchmarkComparisonHistory.model_validate(
        history.model_dump(mode="python")
    )
    restored_document = RecoveryBenchmarkComparisonHistoryDocument.model_validate(
        document.model_dump(mode="python")
    )

    assert restored_history.schema_version == RecoveryBenchmarkComparisonHistorySchemaVersion.V1
    assert restored_document.schema_version == RecoveryBenchmarkComparisonHistorySchemaVersion.V1
    assert restored_document.history.overall_decision == RecoveryBenchmarkQualityGateDecision.WARNING


def test_save_and_load_history_roundtrip(artifact_tmp_path) -> None:
    persistence = RecoveryBenchmarkComparisonPersistenceService()
    service = RecoveryBenchmarkComparisonHistoryService()
    catalog_dir = _test_dir(artifact_tmp_path, "save-load-source")
    output_path = _test_dir(artifact_tmp_path, "save-load-output") / "history.json"
    persistence.save_to_catalog(comparison=_passed_comparison(), catalog_dir=str(catalog_dir))
    history = service.build_history(str(catalog_dir), history_id="history:save-load")

    entry = service.save_history(history=history, output_path=str(output_path))
    restored = service.load_history(str(output_path))

    assert entry.history_id == "history:save-load"
    assert restored.history_id == history.history_id
    assert restored.overall_decision == RecoveryBenchmarkQualityGateDecision.PASSED


def test_save_to_catalog_and_list_catalog_return_sorted_history_entries(artifact_tmp_path) -> None:
    service = RecoveryBenchmarkComparisonHistoryService()
    catalog_dir = _test_dir(artifact_tmp_path, "history-catalog")
    first = RecoveryBenchmarkComparisonHistory(
        history_id="history:a",
        source_catalog_dir="source-a",
        policy=RecoveryBenchmarkQualityGatePolicy(),
        overall_decision=RecoveryBenchmarkQualityGateDecision.PASSED,
        evaluated_comparisons=1,
        passed_comparisons=1,
        warning_comparisons=0,
        failed_comparisons=0,
        entries=[],
        violations=[],
        summary="history a summary",
    )
    second = RecoveryBenchmarkComparisonHistory(
        history_id="history:b",
        source_catalog_dir="source-b",
        policy=RecoveryBenchmarkQualityGatePolicy(),
        overall_decision=RecoveryBenchmarkQualityGateDecision.FAILED,
        evaluated_comparisons=1,
        passed_comparisons=0,
        warning_comparisons=0,
        failed_comparisons=1,
        entries=[],
        violations=[],
        summary="history b summary",
    )

    service.save_to_catalog(history=second, catalog_dir=str(catalog_dir))
    service.save_to_catalog(history=first, catalog_dir=str(catalog_dir))
    catalog = service.list_catalog(str(catalog_dir))

    assert isinstance(catalog, RecoveryBenchmarkComparisonHistoryCatalog)
    assert [entry.history_id for entry in catalog.entries] == ["history:a", "history:b"]
    assert all(Path(entry.path).exists() for entry in catalog.entries)


def test_invalid_history_document_raises_value_error(artifact_tmp_path) -> None:
    path = _test_dir(artifact_tmp_path, "invalid-history") / "broken.json"
    path.write_text(json.dumps({"schema_version": "v1", "history": {"oops": True}}), encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid benchmark comparison history document schema"):
        RecoveryBenchmarkComparisonHistoryService().load_history(str(path))


def test_invalid_comparison_document_errors_are_owned_by_persistence_layer(artifact_tmp_path) -> None:
    catalog_dir = _test_dir(artifact_tmp_path, "invalid-comparison")
    path = catalog_dir / "broken.json"
    path.write_text(json.dumps({"schema_version": "v1", "comparison": {"oops": True}}), encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid benchmark comparison document schema"):
        RecoveryBenchmarkComparisonHistoryService().build_history(str(catalog_dir))


def test_history_layer_is_static_and_uses_persisted_comparison_status(artifact_tmp_path) -> None:
    persistence = RecoveryBenchmarkComparisonPersistenceService()
    service = RecoveryBenchmarkComparisonHistoryService()
    catalog_dir = _test_dir(artifact_tmp_path, "static")
    comparison = _failed_comparison()
    persistence.save_to_catalog(comparison=comparison, catalog_dir=str(catalog_dir))

    history = service.build_history(str(catalog_dir))

    assert comparison.status == RecoveryBenchmarkComparisonStatus.REGRESSED
    assert history.entries[0].status == RecoveryBenchmarkComparisonStatus.REGRESSED
    assert history.overall_decision == RecoveryBenchmarkQualityGateDecision.FAILED


