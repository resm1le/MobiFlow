from __future__ import annotations

"""Benchmark comparison assets and services."""

from enum import Enum

from pydantic import Field

from mobiflow_agent.common.contracts import StrictModel

class RecoveryBenchmarkRunReportComparisonSchemaVersion(str, Enum):
    V1 = "v1"

class RecoveryBenchmarkComparisonStatus(str, Enum):
    IMPROVED = "improved"
    REGRESSED = "regressed"
    UNCHANGED = "unchanged"
    MIXED = "mixed"
    INCOMPATIBLE = "incompatible"

class RecoveryBenchmarkCaseDeltaStatus(str, Enum):
    NEWLY_PASSING = "newly_passing"
    NEWLY_FAILING = "newly_failing"
    UNCHANGED_PASSING = "unchanged_passing"
    UNCHANGED_FAILING = "unchanged_failing"
    ADDED = "added"
    REMOVED = "removed"

class RecoveryBenchmarkCaseResultDelta(StrictModel):
    benchmark_case_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    baseline_matched: bool | None = None
    candidate_matched: bool | None = None
    status: RecoveryBenchmarkCaseDeltaStatus
    summary: str = Field(min_length=1)

class RecoveryBenchmarkDatasetRunReportComparison(StrictModel):
    schema_version: RecoveryBenchmarkRunReportComparisonSchemaVersion = (
        RecoveryBenchmarkRunReportComparisonSchemaVersion.V1
    )
    baseline_dataset_id: str = Field(min_length=1)
    candidate_dataset_id: str = Field(min_length=1)
    dataset_name: str = Field(min_length=1)
    status: RecoveryBenchmarkComparisonStatus
    baseline_match_rate: float = Field(ge=0.0, le=1.0)
    candidate_match_rate: float = Field(ge=0.0, le=1.0)
    match_rate_delta: float
    baseline_matched_cases: int = Field(ge=0)
    candidate_matched_cases: int = Field(ge=0)
    matched_cases_delta: int
    baseline_mismatched_cases: int = Field(ge=0)
    candidate_mismatched_cases: int = Field(ge=0)
    mismatched_cases_delta: int
    case_deltas: list[RecoveryBenchmarkCaseResultDelta] = Field(default_factory=list)
    summary: str = Field(min_length=1)

class RecoveryBenchmarkRunReportCatalogComparison(StrictModel):
    schema_version: RecoveryBenchmarkRunReportComparisonSchemaVersion = (
        RecoveryBenchmarkRunReportComparisonSchemaVersion.V1
    )
    baseline_catalog_dir: str = Field(min_length=1)
    candidate_catalog_dir: str = Field(min_length=1)
    compared_datasets: int = Field(ge=0)
    improved_datasets: int = Field(ge=0)
    regressed_datasets: int = Field(ge=0)
    unchanged_datasets: int = Field(ge=0)
    mixed_datasets: int = Field(ge=0)
    incompatible_datasets: int = Field(ge=0)
    missing_baseline_dataset_ids: list[str] = Field(default_factory=list)
    missing_candidate_dataset_ids: list[str] = Field(default_factory=list)
    comparisons: list[RecoveryBenchmarkDatasetRunReportComparison] = Field(default_factory=list)
    summary: str = Field(min_length=1)

from enum import Enum

from pydantic import Field

from mobiflow_agent.common.contracts import StrictModel
class RecoveryBenchmarkComparisonDocumentSchemaVersion(str, Enum):
    V1 = "v1"

class RecoveryBenchmarkComparisonKind(str, Enum):
    DATASET = "dataset"
    CATALOG = "catalog"

class RecoveryBenchmarkDatasetComparisonDocument(StrictModel):
    schema_version: RecoveryBenchmarkComparisonDocumentSchemaVersion = (
        RecoveryBenchmarkComparisonDocumentSchemaVersion.V1
    )
    comparison: RecoveryBenchmarkDatasetRunReportComparison

class RecoveryBenchmarkCatalogComparisonDocument(StrictModel):
    schema_version: RecoveryBenchmarkComparisonDocumentSchemaVersion = (
        RecoveryBenchmarkComparisonDocumentSchemaVersion.V1
    )
    comparison: RecoveryBenchmarkRunReportCatalogComparison

class RecoveryBenchmarkComparisonCatalogEntry(StrictModel):
    comparison_id: str = Field(min_length=1)
    comparison_kind: RecoveryBenchmarkComparisonKind
    baseline_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    status: RecoveryBenchmarkComparisonStatus
    path: str = Field(min_length=1)
    summary: str = Field(min_length=1)

class RecoveryBenchmarkComparisonCatalog(StrictModel):
    schema_version: RecoveryBenchmarkComparisonDocumentSchemaVersion = (
        RecoveryBenchmarkComparisonDocumentSchemaVersion.V1
    )
    catalog_dir: str = Field(min_length=1)
    entries: list[RecoveryBenchmarkComparisonCatalogEntry] = Field(default_factory=list)
    summary: str = Field(min_length=1)

import json
from hashlib import sha256
from pathlib import Path
from urllib.parse import quote

from pydantic import ValidationError

ComparisonDocument = RecoveryBenchmarkDatasetComparisonDocument | RecoveryBenchmarkCatalogComparisonDocument
Comparison = RecoveryBenchmarkDatasetRunReportComparison | RecoveryBenchmarkRunReportCatalogComparison

class RecoveryBenchmarkComparisonPersistenceService:
    def save_dataset_comparison(
        self,
        *,
        comparison: RecoveryBenchmarkDatasetRunReportComparison,
        output_path: str,
    ) -> RecoveryBenchmarkComparisonCatalogEntry:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        document = RecoveryBenchmarkDatasetComparisonDocument(comparison=comparison)
        self._write_document(path=path, document=document)
        return self._build_dataset_entry(comparison=comparison, path=path)

    def load_dataset_comparison(self, path: str) -> RecoveryBenchmarkDatasetRunReportComparison:
        document = self._load_document(Path(path))
        if not isinstance(document, RecoveryBenchmarkDatasetComparisonDocument):
            raise ValueError(f"Invalid benchmark dataset comparison document schema: {path}")
        return document.comparison

    def save_catalog_comparison(
        self,
        *,
        comparison: RecoveryBenchmarkRunReportCatalogComparison,
        output_path: str,
    ) -> RecoveryBenchmarkComparisonCatalogEntry:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        document = RecoveryBenchmarkCatalogComparisonDocument(comparison=comparison)
        self._write_document(path=path, document=document)
        return self._build_catalog_entry(comparison=comparison, path=path)

    def load_catalog_comparison(self, path: str) -> RecoveryBenchmarkRunReportCatalogComparison:
        document = self._load_document(Path(path))
        if not isinstance(document, RecoveryBenchmarkCatalogComparisonDocument):
            raise ValueError(f"Invalid benchmark catalog comparison document schema: {path}")
        return document.comparison

    def save_to_catalog(
        self,
        *,
        comparison: Comparison,
        catalog_dir: str,
    ) -> RecoveryBenchmarkComparisonCatalogEntry:
        directory = Path(catalog_dir)
        if isinstance(comparison, RecoveryBenchmarkDatasetRunReportComparison):
            path = self._catalog_path(directory, self._dataset_comparison_id(comparison))
            return self.save_dataset_comparison(comparison=comparison, output_path=str(path))
        path = self._catalog_path(directory, self._catalog_comparison_id(comparison))
        return self.save_catalog_comparison(comparison=comparison, output_path=str(path))

    def list_catalog(self, catalog_dir: str) -> RecoveryBenchmarkComparisonCatalog:
        directory = Path(catalog_dir)
        if not directory.exists():
            raise FileNotFoundError(f"Comparison catalog directory does not exist: {directory}")

        entries: list[RecoveryBenchmarkComparisonCatalogEntry] = []
        for path, document in self._iter_catalog_documents(directory):
            if isinstance(document, RecoveryBenchmarkDatasetComparisonDocument):
                entries.append(self._build_dataset_entry(comparison=document.comparison, path=path))
            else:
                entries.append(self._build_catalog_entry(comparison=document.comparison, path=path))
        entries.sort(key=lambda item: item.comparison_id)
        summary = f"Benchmark comparison catalog {directory} contains {len(entries)} comparisons."
        return RecoveryBenchmarkComparisonCatalog(
            catalog_dir=str(directory),
            entries=entries,
            summary=summary,
        )

    def _iter_catalog_documents(self, directory: Path) -> list[tuple[Path, ComparisonDocument]]:
        documents: list[tuple[Path, ComparisonDocument]] = []
        for path in sorted(directory.glob("*.json"), key=lambda item: item.name):
            documents.append((path, self._load_document(path)))
        return documents

    @staticmethod
    def _write_document(*, path: Path, document: ComparisonDocument) -> None:
        payload = document.model_dump(mode="json")
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def _load_document(path: Path) -> ComparisonDocument:
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid benchmark comparison JSON document: {path}") from exc

        dataset_error: ValidationError | None = None
        try:
            return RecoveryBenchmarkDatasetComparisonDocument.model_validate(payload)
        except ValidationError as exc:
            dataset_error = exc

        try:
            return RecoveryBenchmarkCatalogComparisonDocument.model_validate(payload)
        except ValidationError as exc:
            raise ValueError(f"Invalid benchmark comparison document schema: {path}") from (
                dataset_error or exc
            )

    @staticmethod
    def _build_dataset_entry(
        *,
        comparison: RecoveryBenchmarkDatasetRunReportComparison,
        path: Path,
    ) -> RecoveryBenchmarkComparisonCatalogEntry:
        return RecoveryBenchmarkComparisonCatalogEntry(
            comparison_id=RecoveryBenchmarkComparisonPersistenceService._dataset_comparison_id(comparison),
            comparison_kind=RecoveryBenchmarkComparisonKind.DATASET,
            baseline_id=comparison.baseline_dataset_id,
            candidate_id=comparison.candidate_dataset_id,
            status=comparison.status,
            path=str(path),
            summary=comparison.summary,
        )

    @staticmethod
    def _build_catalog_entry(
        *,
        comparison: RecoveryBenchmarkRunReportCatalogComparison,
        path: Path,
    ) -> RecoveryBenchmarkComparisonCatalogEntry:
        return RecoveryBenchmarkComparisonCatalogEntry(
            comparison_id=RecoveryBenchmarkComparisonPersistenceService._catalog_comparison_id(comparison),
            comparison_kind=RecoveryBenchmarkComparisonKind.CATALOG,
            baseline_id=comparison.baseline_catalog_dir,
            candidate_id=comparison.candidate_catalog_dir,
            status=RecoveryBenchmarkComparisonPersistenceService._catalog_status(comparison),
            path=str(path),
            summary=comparison.summary,
        )

    @staticmethod
    def _dataset_comparison_id(comparison: RecoveryBenchmarkDatasetRunReportComparison) -> str:
        return f"dataset:{comparison.baseline_dataset_id}:{comparison.candidate_dataset_id}"

    @staticmethod
    def _catalog_comparison_id(comparison: RecoveryBenchmarkRunReportCatalogComparison) -> str:
        baseline_id = RecoveryBenchmarkComparisonPersistenceService._safe_path_id(
            comparison.baseline_catalog_dir
        )
        candidate_id = RecoveryBenchmarkComparisonPersistenceService._safe_path_id(
            comparison.candidate_catalog_dir
        )
        return f"catalog:{baseline_id}:{candidate_id}"

    @staticmethod
    def _safe_path_id(path: str) -> str:
        return str(Path(path).resolve()).replace("\\", "/").replace("/", "__")

    @staticmethod
    def _catalog_status(
        comparison: RecoveryBenchmarkRunReportCatalogComparison,
    ) -> RecoveryBenchmarkComparisonStatus:
        if comparison.regressed_datasets > 0:
            return RecoveryBenchmarkComparisonStatus.REGRESSED
        if comparison.incompatible_datasets > 0:
            return RecoveryBenchmarkComparisonStatus.INCOMPATIBLE
        if comparison.mixed_datasets > 0:
            return RecoveryBenchmarkComparisonStatus.MIXED
        if comparison.improved_datasets > 0:
            return RecoveryBenchmarkComparisonStatus.IMPROVED
        return RecoveryBenchmarkComparisonStatus.UNCHANGED

    @staticmethod
    def _catalog_path(directory: Path, comparison_id: str) -> Path:
        encoded_comparison_id = quote(comparison_id, safe="-_")
        if len(encoded_comparison_id) > 120:
            digest = sha256(comparison_id.encode("utf-8")).hexdigest()
            encoded_comparison_id = f"comparison-{digest}"
        return directory / f"{encoded_comparison_id}.json"

from pathlib import Path

from mobiflow_agent.evaluation.benchmark.suite import RecoveryBenchmarkCaseResult
from mobiflow_agent.evaluation.benchmark.run_report import (
    RecoveryBenchmarkDatasetRunReportPersistenceService,
)
from mobiflow_agent.evaluation.benchmark.run_report import RecoveryBenchmarkDatasetRunReport
CaseKey = tuple[str, str]

class RecoveryBenchmarkRunReportComparisonService:
    def __init__(self) -> None:
        self._persistence_service = RecoveryBenchmarkDatasetRunReportPersistenceService()

    def compare_reports(
        self,
        *,
        baseline: RecoveryBenchmarkDatasetRunReport,
        candidate: RecoveryBenchmarkDatasetRunReport,
    ) -> RecoveryBenchmarkDatasetRunReportComparison:
        if baseline.dataset_id != candidate.dataset_id:
            return self._build_comparison(
                baseline=baseline,
                candidate=candidate,
                case_deltas=[],
                status=RecoveryBenchmarkComparisonStatus.INCOMPATIBLE,
            )

        baseline_cases = self._case_results_by_key(baseline)
        candidate_cases = self._case_results_by_key(candidate)
        case_deltas = self._build_case_deltas(
            baseline_cases=baseline_cases,
            candidate_cases=candidate_cases,
        )
        status = self._classify_comparison(
            baseline=baseline,
            candidate=candidate,
            case_deltas=case_deltas,
        )
        return self._build_comparison(
            baseline=baseline,
            candidate=candidate,
            case_deltas=case_deltas,
            status=status,
        )

    def compare_report_files(
        self,
        *,
        baseline_path: str,
        candidate_path: str,
    ) -> RecoveryBenchmarkDatasetRunReportComparison:
        baseline = self._persistence_service.load_report(baseline_path)
        candidate = self._persistence_service.load_report(candidate_path)
        return self.compare_reports(baseline=baseline, candidate=candidate)

    def compare_catalog_dataset(
        self,
        *,
        baseline_catalog_dir: str,
        candidate_catalog_dir: str,
        dataset_id: str,
    ) -> RecoveryBenchmarkDatasetRunReportComparison:
        baseline = self._persistence_service.load_from_catalog(
            catalog_dir=baseline_catalog_dir,
            dataset_id=dataset_id,
        )
        candidate = self._persistence_service.load_from_catalog(
            catalog_dir=candidate_catalog_dir,
            dataset_id=dataset_id,
        )
        return self.compare_reports(baseline=baseline, candidate=candidate)

    def compare_catalogs(
        self,
        *,
        baseline_catalog_dir: str,
        candidate_catalog_dir: str,
    ) -> RecoveryBenchmarkRunReportCatalogComparison:
        resolved_baseline_dir = str(Path(baseline_catalog_dir).resolve())
        resolved_candidate_dir = str(Path(candidate_catalog_dir).resolve())
        baseline_catalog = self._persistence_service.list_catalog(resolved_baseline_dir)
        candidate_catalog = self._persistence_service.list_catalog(resolved_candidate_dir)
        baseline_ids = {entry.dataset_id for entry in baseline_catalog.entries}
        candidate_ids = {entry.dataset_id for entry in candidate_catalog.entries}
        common_ids = sorted(baseline_ids & candidate_ids)
        missing_baseline_ids = sorted(candidate_ids - baseline_ids)
        missing_candidate_ids = sorted(baseline_ids - candidate_ids)
        comparisons = [
            self.compare_catalog_dataset(
                baseline_catalog_dir=resolved_baseline_dir,
                candidate_catalog_dir=resolved_candidate_dir,
                dataset_id=dataset_id,
            )
            for dataset_id in common_ids
        ]
        improved = sum(1 for item in comparisons if item.status == RecoveryBenchmarkComparisonStatus.IMPROVED)
        regressed = sum(1 for item in comparisons if item.status == RecoveryBenchmarkComparisonStatus.REGRESSED)
        unchanged = sum(1 for item in comparisons if item.status == RecoveryBenchmarkComparisonStatus.UNCHANGED)
        mixed = sum(1 for item in comparisons if item.status == RecoveryBenchmarkComparisonStatus.MIXED)
        incompatible = sum(1 for item in comparisons if item.status == RecoveryBenchmarkComparisonStatus.INCOMPATIBLE)
        summary = (
            f"Benchmark run report catalogs compared: {len(comparisons)} shared datasets, "
            f"{improved} improved, {regressed} regressed, {unchanged} unchanged, "
            f"{mixed} mixed, {incompatible} incompatible."
        )
        return RecoveryBenchmarkRunReportCatalogComparison(
            baseline_catalog_dir=resolved_baseline_dir,
            candidate_catalog_dir=resolved_candidate_dir,
            compared_datasets=len(comparisons),
            improved_datasets=improved,
            regressed_datasets=regressed,
            unchanged_datasets=unchanged,
            mixed_datasets=mixed,
            incompatible_datasets=incompatible,
            missing_baseline_dataset_ids=missing_baseline_ids,
            missing_candidate_dataset_ids=missing_candidate_ids,
            comparisons=comparisons,
            summary=summary,
        )

    @staticmethod
    def _case_results_by_key(report: RecoveryBenchmarkDatasetRunReport) -> dict[CaseKey, RecoveryBenchmarkCaseResult]:
        results: dict[CaseKey, RecoveryBenchmarkCaseResult] = {}
        for suite_report in report.result.suite_reports:
            for result in suite_report.results:
                results[(result.benchmark_case_id, result.case_id)] = result
        return results

    def _build_case_deltas(
        self,
        *,
        baseline_cases: dict[CaseKey, RecoveryBenchmarkCaseResult],
        candidate_cases: dict[CaseKey, RecoveryBenchmarkCaseResult],
    ) -> list[RecoveryBenchmarkCaseResultDelta]:
        deltas: list[RecoveryBenchmarkCaseResultDelta] = []
        for key in sorted(baseline_cases.keys() | candidate_cases.keys()):
            baseline_result = baseline_cases.get(key)
            candidate_result = candidate_cases.get(key)
            status = self._classify_case_delta(baseline_result, candidate_result)
            benchmark_case_id, case_id = key
            deltas.append(
                RecoveryBenchmarkCaseResultDelta(
                    benchmark_case_id=benchmark_case_id,
                    case_id=case_id,
                    baseline_matched=baseline_result.matched if baseline_result is not None else None,
                    candidate_matched=candidate_result.matched if candidate_result is not None else None,
                    status=status,
                    summary=(
                        f"Benchmark case {benchmark_case_id} / {case_id} "
                        f"comparison status is {status.value}."
                    ),
                )
            )
        return deltas

    @staticmethod
    def _classify_case_delta(
        baseline_result: RecoveryBenchmarkCaseResult | None,
        candidate_result: RecoveryBenchmarkCaseResult | None,
    ) -> RecoveryBenchmarkCaseDeltaStatus:
        if baseline_result is None:
            return RecoveryBenchmarkCaseDeltaStatus.ADDED
        if candidate_result is None:
            return RecoveryBenchmarkCaseDeltaStatus.REMOVED
        if baseline_result.matched and candidate_result.matched:
            return RecoveryBenchmarkCaseDeltaStatus.UNCHANGED_PASSING
        if not baseline_result.matched and not candidate_result.matched:
            return RecoveryBenchmarkCaseDeltaStatus.UNCHANGED_FAILING
        if baseline_result.matched and not candidate_result.matched:
            return RecoveryBenchmarkCaseDeltaStatus.NEWLY_FAILING
        return RecoveryBenchmarkCaseDeltaStatus.NEWLY_PASSING

    @staticmethod
    def _classify_comparison(
        *,
        baseline: RecoveryBenchmarkDatasetRunReport,
        candidate: RecoveryBenchmarkDatasetRunReport,
        case_deltas: list[RecoveryBenchmarkCaseResultDelta],
    ) -> RecoveryBenchmarkComparisonStatus:
        delta = candidate.result.match_rate - baseline.result.match_rate
        statuses = {item.status for item in case_deltas}
        has_new_failure = RecoveryBenchmarkCaseDeltaStatus.NEWLY_FAILING in statuses
        has_new_passing = RecoveryBenchmarkCaseDeltaStatus.NEWLY_PASSING in statuses
        has_added = RecoveryBenchmarkCaseDeltaStatus.ADDED in statuses
        has_removed = RecoveryBenchmarkCaseDeltaStatus.REMOVED in statuses
        if delta < 0 or has_new_failure:
            return RecoveryBenchmarkComparisonStatus.REGRESSED
        if delta > 0 and not has_new_failure and not has_removed:
            return RecoveryBenchmarkComparisonStatus.IMPROVED
        if (
            delta == 0
            and not has_added
            and not has_removed
            and not has_new_failure
            and not has_new_passing
        ):
            return RecoveryBenchmarkComparisonStatus.UNCHANGED
        return RecoveryBenchmarkComparisonStatus.MIXED

    @staticmethod
    def _build_comparison(
        *,
        baseline: RecoveryBenchmarkDatasetRunReport,
        candidate: RecoveryBenchmarkDatasetRunReport,
        case_deltas: list[RecoveryBenchmarkCaseResultDelta],
        status: RecoveryBenchmarkComparisonStatus,
    ) -> RecoveryBenchmarkDatasetRunReportComparison:
        baseline_result = baseline.result
        candidate_result = candidate.result
        summary = (
            f"Benchmark dataset {baseline.dataset_id} comparison is {status.value}: "
            f"match rate {baseline_result.match_rate:.4f} -> {candidate_result.match_rate:.4f}."
        )
        return RecoveryBenchmarkDatasetRunReportComparison(
            baseline_dataset_id=baseline.dataset_id,
            candidate_dataset_id=candidate.dataset_id,
            dataset_name=candidate.dataset_name,
            status=status,
            baseline_match_rate=baseline_result.match_rate,
            candidate_match_rate=candidate_result.match_rate,
            match_rate_delta=candidate_result.match_rate - baseline_result.match_rate,
            baseline_matched_cases=baseline_result.matched_cases,
            candidate_matched_cases=candidate_result.matched_cases,
            matched_cases_delta=candidate_result.matched_cases - baseline_result.matched_cases,
            baseline_mismatched_cases=baseline_result.mismatched_cases,
            candidate_mismatched_cases=candidate_result.mismatched_cases,
            mismatched_cases_delta=candidate_result.mismatched_cases - baseline_result.mismatched_cases,
            case_deltas=case_deltas,
            summary=summary,
        )
