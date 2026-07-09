from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import pytest

from tests.artifacts import artifact_dir

from mobiflow_agent.common.contracts import VerificationStatus
from mobiflow_agent.evaluation.benchmark.suite import (
    RecoveryBenchmarkCaseResult,
    RecoveryBenchmarkReport,
)
from mobiflow_agent.evaluation.benchmark.comparison import (
    RecoveryBenchmarkCatalogComparisonDocument,
    RecoveryBenchmarkComparisonCatalog,
    RecoveryBenchmarkComparisonDocumentSchemaVersion,
    RecoveryBenchmarkComparisonKind,
    RecoveryBenchmarkDatasetComparisonDocument,
)
from mobiflow_agent.evaluation.benchmark.comparison import (
    RecoveryBenchmarkComparisonPersistenceService,
)
from mobiflow_agent.evaluation.benchmark.dataset import RecoveryBenchmarkDatasetResult
from mobiflow_agent.evaluation.benchmark.run_report import (
    RecoveryBenchmarkDatasetRunReportPersistenceService,
)
from mobiflow_agent.evaluation.benchmark.run_report import RecoveryBenchmarkDatasetRunReport
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
    matched: bool = True,
) -> RecoveryBenchmarkDatasetRunReport:
    cases = [_case_result("benchmark-case:1", "eval:1", matched=matched)]
    matched_cases = sum(1 for case in cases if case.matched)
    mismatched_cases = len(cases) - matched_cases
    match_rate = matched_cases / len(cases)
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
    baseline_matched: bool = False,
    candidate_matched: bool = True,
):
    baseline = _report(dataset_id=dataset_id, matched=baseline_matched)
    candidate = _report(dataset_id=dataset_id, matched=candidate_matched)
    return RecoveryBenchmarkRunReportComparisonService().compare_reports(
        baseline=baseline,
        candidate=candidate,
    )


def _catalog_comparison(tmp_path: Path) -> RecoveryBenchmarkRunReportCatalogComparison:
    report_persistence = RecoveryBenchmarkDatasetRunReportPersistenceService()
    comparison_service = RecoveryBenchmarkRunReportComparisonService()
    baseline_dir = tmp_path / "baseline"
    candidate_dir = tmp_path / "candidate"
    report_persistence.save_to_catalog(
        report=_report(dataset_id="benchmark-dataset:alpha", matched=False),
        catalog_dir=str(baseline_dir),
    )
    report_persistence.save_to_catalog(
        report=_report(dataset_id="benchmark-dataset:alpha", matched=True),
        catalog_dir=str(candidate_dir),
    )
    return comparison_service.compare_catalogs(
        baseline_catalog_dir=str(baseline_dir),
        candidate_catalog_dir=str(candidate_dir),
    )


def _test_dir(artifact_tmp_path: Path, name: str) -> Path:
    return artifact_dir(artifact_tmp_path, name)


def test_save_dataset_comparison_writes_json_document(artifact_tmp_path) -> None:
    service = RecoveryBenchmarkComparisonPersistenceService()
    comparison = _dataset_comparison()
    output_path = _test_dir(artifact_tmp_path, "save-dataset") / "nested" / "comparison.json"

    entry = service.save_dataset_comparison(comparison=comparison, output_path=str(output_path))

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == RecoveryBenchmarkComparisonDocumentSchemaVersion.V1.value
    assert payload["comparison"]["baseline_dataset_id"] == comparison.baseline_dataset_id
    assert entry.comparison_kind == RecoveryBenchmarkComparisonKind.DATASET
    assert entry.status == comparison.status


def test_load_dataset_comparison_restores_comparison(artifact_tmp_path) -> None:
    service = RecoveryBenchmarkComparisonPersistenceService()
    comparison = _dataset_comparison()
    output_path = _test_dir(artifact_tmp_path, "load-dataset") / "comparison.json"
    service.save_dataset_comparison(comparison=comparison, output_path=str(output_path))

    restored = service.load_dataset_comparison(str(output_path))

    assert restored.baseline_dataset_id == comparison.baseline_dataset_id
    assert restored.status == RecoveryBenchmarkComparisonStatus.IMPROVED


def test_save_catalog_comparison_writes_json_document(artifact_tmp_path) -> None:
    service = RecoveryBenchmarkComparisonPersistenceService()
    tmp_path = _test_dir(artifact_tmp_path, "save-catalog-comparison")
    comparison = _catalog_comparison(tmp_path)
    output_path = tmp_path / "comparison-docs" / "catalog-comparison.json"

    entry = service.save_catalog_comparison(comparison=comparison, output_path=str(output_path))

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == RecoveryBenchmarkComparisonDocumentSchemaVersion.V1.value
    assert payload["comparison"]["baseline_catalog_dir"] == comparison.baseline_catalog_dir
    assert entry.comparison_kind == RecoveryBenchmarkComparisonKind.CATALOG
    assert entry.status == RecoveryBenchmarkComparisonStatus.IMPROVED


def test_load_catalog_comparison_restores_comparison(artifact_tmp_path) -> None:
    service = RecoveryBenchmarkComparisonPersistenceService()
    tmp_path = _test_dir(artifact_tmp_path, "load-catalog-comparison")
    comparison = _catalog_comparison(tmp_path)
    output_path = tmp_path / "catalog-comparison.json"
    service.save_catalog_comparison(comparison=comparison, output_path=str(output_path))

    restored = service.load_catalog_comparison(str(output_path))

    assert restored.baseline_catalog_dir == comparison.baseline_catalog_dir
    assert restored.improved_datasets == 1


def test_comparison_documents_support_roundtrip(artifact_tmp_path) -> None:
    tmp_path = _test_dir(artifact_tmp_path, "roundtrip")
    dataset_document = RecoveryBenchmarkDatasetComparisonDocument(
        comparison=_dataset_comparison(),
    )
    catalog_document = RecoveryBenchmarkCatalogComparisonDocument(
        comparison=_catalog_comparison(tmp_path),
    )

    restored_dataset = RecoveryBenchmarkDatasetComparisonDocument.model_validate(
        dataset_document.model_dump(mode="python")
    )
    restored_catalog = RecoveryBenchmarkCatalogComparisonDocument.model_validate(
        catalog_document.model_dump(mode="python")
    )

    assert restored_dataset.schema_version == RecoveryBenchmarkComparisonDocumentSchemaVersion.V1
    assert restored_catalog.schema_version == RecoveryBenchmarkComparisonDocumentSchemaVersion.V1


def test_save_to_catalog_writes_kind_specific_dataset_comparison_file(artifact_tmp_path) -> None:
    service = RecoveryBenchmarkComparisonPersistenceService()
    comparison = _dataset_comparison()
    catalog_dir = _test_dir(artifact_tmp_path, "save-dataset-to-catalog")

    entry = service.save_to_catalog(comparison=comparison, catalog_dir=str(catalog_dir))

    expected_id = f"dataset:{comparison.baseline_dataset_id}:{comparison.candidate_dataset_id}"
    assert entry.comparison_id == expected_id
    assert entry.path == str(catalog_dir / f"{quote(expected_id, safe='-_')}.json")
    assert Path(entry.path).exists()


def test_save_to_catalog_writes_kind_specific_catalog_comparison_file(artifact_tmp_path) -> None:
    service = RecoveryBenchmarkComparisonPersistenceService()
    tmp_path = _test_dir(artifact_tmp_path, "save-catalog-to-catalog")
    comparison = _catalog_comparison(tmp_path)
    catalog_dir = tmp_path / "comparison-catalog"

    entry = service.save_to_catalog(comparison=comparison, catalog_dir=str(catalog_dir))

    assert entry.comparison_kind == RecoveryBenchmarkComparisonKind.CATALOG
    assert entry.comparison_id.startswith("catalog:")
    assert Path(entry.path).exists()


def test_list_catalog_returns_entries_sorted_by_comparison_id(artifact_tmp_path) -> None:
    service = RecoveryBenchmarkComparisonPersistenceService()
    catalog_dir = _test_dir(artifact_tmp_path, "list-catalog")
    second = _dataset_comparison(dataset_id="benchmark-dataset:b")
    first = _dataset_comparison(dataset_id="benchmark-dataset:a")
    service.save_to_catalog(comparison=second, catalog_dir=str(catalog_dir))
    service.save_to_catalog(comparison=first, catalog_dir=str(catalog_dir))

    catalog = service.list_catalog(str(catalog_dir))

    assert isinstance(catalog, RecoveryBenchmarkComparisonCatalog)
    assert [entry.comparison_id for entry in catalog.entries] == sorted(
        entry.comparison_id for entry in catalog.entries
    )


def test_load_dataset_comparison_rejects_invalid_json(artifact_tmp_path) -> None:
    path = _test_dir(artifact_tmp_path, "bad-json") / "invalid.json"
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid benchmark comparison JSON document"):
        RecoveryBenchmarkComparisonPersistenceService().load_dataset_comparison(str(path))


def test_load_dataset_comparison_rejects_unsupported_schema_version(artifact_tmp_path) -> None:
    path = _test_dir(artifact_tmp_path, "bad-schema") / "bad-schema.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "v999",
                "comparison": _dataset_comparison().model_dump(mode="json"),
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Invalid benchmark comparison document schema"):
        RecoveryBenchmarkComparisonPersistenceService().load_dataset_comparison(str(path))


def test_list_catalog_rejects_invalid_comparison_document(artifact_tmp_path) -> None:
    catalog_dir = _test_dir(artifact_tmp_path, "invalid-catalog")
    invalid_path = catalog_dir / "broken.json"
    invalid_path.write_text(
        json.dumps({"schema_version": "v1", "comparison": {"oops": True}}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Invalid benchmark comparison document schema"):
        RecoveryBenchmarkComparisonPersistenceService().list_catalog(str(catalog_dir))


def test_persistence_layer_is_static_and_does_not_rerun_comparison(artifact_tmp_path) -> None:
    service = RecoveryBenchmarkComparisonPersistenceService()
    comparison = _dataset_comparison(baseline_matched=True, candidate_matched=False)
    catalog_dir = _test_dir(artifact_tmp_path, "pure")

    entry = service.save_to_catalog(comparison=comparison, catalog_dir=str(catalog_dir))
    restored = service.load_dataset_comparison(entry.path)
    catalog = service.list_catalog(str(catalog_dir))

    assert restored.status == RecoveryBenchmarkComparisonStatus.REGRESSED
    assert catalog.entries[0].status == RecoveryBenchmarkComparisonStatus.REGRESSED


