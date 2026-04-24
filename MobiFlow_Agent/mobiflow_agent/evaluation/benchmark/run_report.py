from __future__ import annotations

"""Benchmark run-report assets and persistence/runner services."""

from enum import Enum

from pydantic import Field

from mobiflow_agent.common.contracts import StrictModel
from mobiflow_agent.evaluation.benchmark.dataset import RecoveryBenchmarkDatasetResult

class RecoveryBenchmarkDatasetRunnerSchemaVersion(str, Enum):
    V1 = "v1"

class RecoveryBenchmarkDatasetRunReport(StrictModel):
    schema_version: RecoveryBenchmarkDatasetRunnerSchemaVersion = (
        RecoveryBenchmarkDatasetRunnerSchemaVersion.V1
    )
    dataset_id: str = Field(min_length=1)
    dataset_name: str = Field(min_length=1)
    source_path: str | None = None
    result: RecoveryBenchmarkDatasetResult
    summary: str = Field(min_length=1)

class RecoveryBenchmarkCatalogRunReport(StrictModel):
    schema_version: RecoveryBenchmarkDatasetRunnerSchemaVersion = (
        RecoveryBenchmarkDatasetRunnerSchemaVersion.V1
    )
    catalog_dir: str = Field(min_length=1)
    total_datasets: int = Field(ge=0)
    total_suites: int = Field(ge=0)
    total_cases: int = Field(ge=0)
    matched_cases: int = Field(ge=0)
    mismatched_cases: int = Field(ge=0)
    match_rate: float = Field(ge=0.0, le=1.0)
    dataset_reports: list[RecoveryBenchmarkDatasetRunReport] = Field(default_factory=list)
    summary: str = Field(min_length=1)

from enum import Enum

from pydantic import Field

from mobiflow_agent.common.contracts import StrictModel

class RecoveryBenchmarkDatasetRunReportDocumentSchemaVersion(str, Enum):
    V1 = "v1"

class RecoveryBenchmarkDatasetRunReportDocument(StrictModel):
    schema_version: RecoveryBenchmarkDatasetRunReportDocumentSchemaVersion = (
        RecoveryBenchmarkDatasetRunReportDocumentSchemaVersion.V1
    )
    report: RecoveryBenchmarkDatasetRunReport

class RecoveryBenchmarkDatasetRunReportCatalogEntry(StrictModel):
    dataset_id: str = Field(min_length=1)
    dataset_name: str = Field(min_length=1)
    source_path: str | None = None
    total_suites: int = Field(ge=0)
    total_cases: int = Field(ge=0)
    matched_cases: int = Field(ge=0)
    mismatched_cases: int = Field(ge=0)
    match_rate: float = Field(ge=0.0, le=1.0)
    path: str = Field(min_length=1)
    summary: str = Field(min_length=1)

class RecoveryBenchmarkDatasetRunReportCatalog(StrictModel):
    schema_version: RecoveryBenchmarkDatasetRunReportDocumentSchemaVersion = (
        RecoveryBenchmarkDatasetRunReportDocumentSchemaVersion.V1
    )
    catalog_dir: str = Field(min_length=1)
    entries: list[RecoveryBenchmarkDatasetRunReportCatalogEntry] = Field(default_factory=list)
    summary: str = Field(min_length=1)

import json
from pathlib import Path
from urllib.parse import quote

from pydantic import ValidationError

class RecoveryBenchmarkDatasetRunReportPersistenceService:
    def save_report(
        self,
        *,
        report: RecoveryBenchmarkDatasetRunReport,
        output_path: str,
    ) -> RecoveryBenchmarkDatasetRunReportCatalogEntry:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        document = RecoveryBenchmarkDatasetRunReportDocument(report=report)
        payload = document.model_dump(mode="json")
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return self._build_catalog_entry(report=report, path=path)

    def load_report(self, path: str) -> RecoveryBenchmarkDatasetRunReport:
        document = self._load_document(Path(path))
        return document.report

    def save_to_catalog(
        self,
        *,
        report: RecoveryBenchmarkDatasetRunReport,
        catalog_dir: str,
    ) -> RecoveryBenchmarkDatasetRunReportCatalogEntry:
        path = self._catalog_path(Path(catalog_dir), report.dataset_id)
        return self.save_report(report=report, output_path=str(path))

    def list_catalog(self, catalog_dir: str) -> RecoveryBenchmarkDatasetRunReportCatalog:
        directory = Path(catalog_dir)
        if not directory.exists():
            raise FileNotFoundError(f"Run report catalog directory does not exist: {directory}")

        entries = [
            self._build_catalog_entry(report=document.report, path=path)
            for path, document in self._iter_catalog_documents(directory)
        ]
        entries.sort(key=lambda item: item.dataset_id)
        summary = (
            f"Benchmark dataset run report catalog {directory} contains "
            f"{len(entries)} reports."
        )
        return RecoveryBenchmarkDatasetRunReportCatalog(
            catalog_dir=str(directory),
            entries=entries,
            summary=summary,
        )

    def load_from_catalog(
        self,
        *,
        catalog_dir: str,
        dataset_id: str,
    ) -> RecoveryBenchmarkDatasetRunReport:
        path = self._catalog_path(Path(catalog_dir), dataset_id)
        return self.load_report(str(path))

    def _iter_catalog_documents(
        self,
        directory: Path,
    ) -> list[tuple[Path, RecoveryBenchmarkDatasetRunReportDocument]]:
        documents: list[tuple[Path, RecoveryBenchmarkDatasetRunReportDocument]] = []
        for path in sorted(directory.glob("*.json"), key=lambda item: item.name):
            documents.append((path, self._load_document(path)))
        return documents

    @staticmethod
    def _load_document(path: Path) -> RecoveryBenchmarkDatasetRunReportDocument:
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid benchmark dataset run report JSON document: {path}") from exc
        try:
            return RecoveryBenchmarkDatasetRunReportDocument.model_validate(payload)
        except ValidationError as exc:
            raise ValueError(
                f"Invalid benchmark dataset run report document schema: {path}"
            ) from exc

    @staticmethod
    def _build_catalog_entry(
        *,
        report: RecoveryBenchmarkDatasetRunReport,
        path: Path,
    ) -> RecoveryBenchmarkDatasetRunReportCatalogEntry:
        result = report.result
        return RecoveryBenchmarkDatasetRunReportCatalogEntry(
            dataset_id=report.dataset_id,
            dataset_name=report.dataset_name,
            source_path=report.source_path,
            total_suites=result.total_suites,
            total_cases=result.total_cases,
            matched_cases=result.matched_cases,
            mismatched_cases=result.mismatched_cases,
            match_rate=result.match_rate,
            path=str(path),
            summary=report.summary,
        )

    @staticmethod
    def _catalog_path(
        directory: Path,
        dataset_id: str,
    ) -> Path:
        encoded_dataset_id = quote(dataset_id, safe="-_")
        return directory / f"{encoded_dataset_id}.json"

from pathlib import Path
from urllib.parse import quote

from mobiflow_agent.evaluation.benchmark.dataset import (
    RecoveryBenchmarkDataset,
    RecoveryBenchmarkDatasetResult,
)
from mobiflow_agent.evaluation.benchmark.dataset_catalog import (
    RecoveryBenchmarkDatasetPersistenceService,
)
from mobiflow_agent.evaluation.benchmark.dataset import RecoveryBenchmarkDatasetService

class RecoveryBenchmarkDatasetRunnerService:
    def __init__(self) -> None:
        self._dataset_service = RecoveryBenchmarkDatasetService()
        self._persistence_service = RecoveryBenchmarkDatasetPersistenceService()

    def run_dataset(self, dataset: RecoveryBenchmarkDataset) -> RecoveryBenchmarkDatasetRunReport:
        result = self._dataset_service.run_dataset(dataset)
        return self._build_dataset_report(
            dataset=dataset,
            source_path=None,
            result=result,
        )

    def run_dataset_file(self, path: str) -> RecoveryBenchmarkDatasetRunReport:
        source_path = str(Path(path).resolve())
        dataset = self._persistence_service.load_dataset(source_path)
        result = self._dataset_service.run_dataset(dataset)
        return self._build_dataset_report(
            dataset=dataset,
            source_path=source_path,
            result=result,
        )

    def run_catalog(self, catalog_dir: str) -> RecoveryBenchmarkCatalogRunReport:
        resolved_catalog_dir = str(Path(catalog_dir).resolve())
        catalog = self._persistence_service.list_catalog(resolved_catalog_dir)
        dataset_reports = [
            self.run_dataset_file(entry.path)
            for entry in catalog.entries
        ]
        total_datasets = len(dataset_reports)
        total_suites = sum(report.result.total_suites for report in dataset_reports)
        total_cases = sum(report.result.total_cases for report in dataset_reports)
        matched_cases = sum(report.result.matched_cases for report in dataset_reports)
        mismatched_cases = sum(report.result.mismatched_cases for report in dataset_reports)
        match_rate = (matched_cases / total_cases) if total_cases else 0.0
        summary = (
            f"Benchmark catalog {resolved_catalog_dir} completed: "
            f"{total_datasets} datasets, {total_suites} suites, {total_cases} cases, "
            f"{matched_cases} matched, {mismatched_cases} mismatched."
        )
        return RecoveryBenchmarkCatalogRunReport(
            catalog_dir=resolved_catalog_dir,
            total_datasets=total_datasets,
            total_suites=total_suites,
            total_cases=total_cases,
            matched_cases=matched_cases,
            mismatched_cases=mismatched_cases,
            match_rate=match_rate,
            dataset_reports=dataset_reports,
            summary=summary,
        )

    def run_catalog_dataset(
        self,
        *,
        catalog_dir: str,
        dataset_id: str,
    ) -> RecoveryBenchmarkDatasetRunReport:
        resolved_catalog_dir = Path(catalog_dir).resolve()
        dataset = self._persistence_service.load_from_catalog(
            catalog_dir=str(resolved_catalog_dir),
            dataset_id=dataset_id,
        )
        result = self._dataset_service.run_dataset(dataset)
        source_path = str(self._catalog_dataset_path(resolved_catalog_dir, dataset_id))
        return self._build_dataset_report(
            dataset=dataset,
            source_path=source_path,
            result=result,
        )

    @staticmethod
    def _build_dataset_report(
        *,
        dataset: RecoveryBenchmarkDataset,
        source_path: str | None,
        result: RecoveryBenchmarkDatasetResult,
    ) -> RecoveryBenchmarkDatasetRunReport:
        summary = (
            f"Benchmark dataset {dataset.name} run completed: "
            f"{result.total_suites} suites, {result.total_cases} cases, "
            f"{result.matched_cases} matched, {result.mismatched_cases} mismatched."
        )
        return RecoveryBenchmarkDatasetRunReport(
            dataset_id=dataset.dataset_id,
            dataset_name=dataset.name,
            source_path=source_path,
            result=result,
            summary=summary,
        )

    @staticmethod
    def _catalog_dataset_path(catalog_dir: Path, dataset_id: str) -> Path:
        return catalog_dir / f"{quote(dataset_id, safe='-_')}.json"
