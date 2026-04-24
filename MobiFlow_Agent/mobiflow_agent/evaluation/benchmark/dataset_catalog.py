from __future__ import annotations

"""Benchmark dataset catalog assets and persistence service."""

from enum import Enum

from pydantic import Field

from mobiflow_agent.common.contracts import StrictModel
from mobiflow_agent.evaluation.benchmark.dataset import RecoveryBenchmarkDataset

class RecoveryBenchmarkDatasetDocumentSchemaVersion(str, Enum):
    V1 = "v1"

class RecoveryBenchmarkDatasetDocument(StrictModel):
    schema_version: RecoveryBenchmarkDatasetDocumentSchemaVersion = (
        RecoveryBenchmarkDatasetDocumentSchemaVersion.V1
    )
    dataset: RecoveryBenchmarkDataset

class RecoveryBenchmarkCatalogEntry(StrictModel):
    dataset_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    source: str = Field(min_length=1)
    suite_count: int = Field(ge=0)
    total_cases: int = Field(ge=0)
    path: str = Field(min_length=1)
    summary: str = Field(min_length=1)

class RecoveryBenchmarkCatalog(StrictModel):
    schema_version: RecoveryBenchmarkDatasetDocumentSchemaVersion = (
        RecoveryBenchmarkDatasetDocumentSchemaVersion.V1
    )
    catalog_dir: str = Field(min_length=1)
    entries: list[RecoveryBenchmarkCatalogEntry] = Field(default_factory=list)
    summary: str = Field(min_length=1)

import json
from pathlib import Path
from urllib.parse import quote

from pydantic import ValidationError

from mobiflow_agent.evaluation.benchmark.dataset import RecoveryBenchmarkDataset
class RecoveryBenchmarkDatasetPersistenceService:
    def save_dataset(
        self,
        *,
        dataset: RecoveryBenchmarkDataset,
        output_path: str,
    ) -> RecoveryBenchmarkCatalogEntry:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        document = RecoveryBenchmarkDatasetDocument(dataset=dataset)
        payload = document.model_dump(mode="json")
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return self._build_catalog_entry(dataset=dataset, path=path)

    def load_dataset(self, path: str) -> RecoveryBenchmarkDataset:
        document = self._load_document(Path(path))
        return document.dataset

    def save_to_catalog(
        self,
        *,
        dataset: RecoveryBenchmarkDataset,
        catalog_dir: str,
    ) -> RecoveryBenchmarkCatalogEntry:
        path = self._catalog_path(Path(catalog_dir), dataset.dataset_id)
        return self.save_dataset(dataset=dataset, output_path=str(path))

    def list_catalog(self, catalog_dir: str) -> RecoveryBenchmarkCatalog:
        directory = Path(catalog_dir)
        if not directory.exists():
            raise FileNotFoundError(f"Catalog directory does not exist: {directory}")

        entries = [
            self._build_catalog_entry(dataset=document.dataset, path=path)
            for path, document in self._iter_catalog_documents(directory)
        ]
        entries.sort(key=lambda item: item.dataset_id)
        summary = (
            f"Benchmark catalog {directory} contains "
            f"{len(entries)} datasets."
        )
        return RecoveryBenchmarkCatalog(
            catalog_dir=str(directory),
            entries=entries,
            summary=summary,
        )

    def load_from_catalog(
        self,
        *,
        catalog_dir: str,
        dataset_id: str,
    ) -> RecoveryBenchmarkDataset:
        path = self._catalog_path(Path(catalog_dir), dataset_id)
        return self.load_dataset(str(path))

    def _iter_catalog_documents(
        self,
        directory: Path,
    ) -> list[tuple[Path, RecoveryBenchmarkDatasetDocument]]:
        documents: list[tuple[Path, RecoveryBenchmarkDatasetDocument]] = []
        for path in sorted(directory.glob("*.json"), key=lambda item: item.name):
            documents.append((path, self._load_document(path)))
        return documents

    @staticmethod
    def _load_document(path: Path) -> RecoveryBenchmarkDatasetDocument:
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid benchmark dataset JSON document: {path}") from exc
        try:
            return RecoveryBenchmarkDatasetDocument.model_validate(payload)
        except ValidationError as exc:
            raise ValueError(f"Invalid benchmark dataset document schema: {path}") from exc

    @staticmethod
    def _build_catalog_entry(
        *,
        dataset: RecoveryBenchmarkDataset,
        path: Path,
    ) -> RecoveryBenchmarkCatalogEntry:
        total_cases = sum(len(suite.cases) for suite in dataset.suites)
        return RecoveryBenchmarkCatalogEntry(
            dataset_id=dataset.dataset_id,
            name=dataset.name,
            source=dataset.source,
            suite_count=len(dataset.suites),
            total_cases=total_cases,
            path=str(path),
            summary=dataset.summary,
        )

    @staticmethod
    def _catalog_path(
        directory: Path,
        dataset_id: str,
    ) -> Path:
        encoded_dataset_id = quote(dataset_id, safe="-_")
        return directory / f"{encoded_dataset_id}.json"
