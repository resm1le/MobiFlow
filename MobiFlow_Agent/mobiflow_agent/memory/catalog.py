from __future__ import annotations

"""Recovery memory catalog assets and persistence/retrieval services."""

import json
from enum import Enum
from hashlib import sha256
from pathlib import Path
from urllib.parse import quote

from pydantic import Field, ValidationError

from mobiflow_agent.common.contracts import StrictModel, VerificationStatus
from mobiflow_agent.execution.followup.decisions import RecoveryFollowupDriverDecision
from mobiflow_agent.memory.case import (
    MemoryCaseRetrievalService,
    RecoveryCaseMatch,
    RecoveryCaseQuery,
    RecoveryCaseRetrievalResponse,
    RecoveryMemoryCase,
)


class MemoryCaseDocumentSchemaVersion(str, Enum):
    V1 = "v1"


class RecoveryMemoryCaseDocument(StrictModel):
    schema_version: MemoryCaseDocumentSchemaVersion = MemoryCaseDocumentSchemaVersion.V1
    case: RecoveryMemoryCase


class RecoveryMemoryCaseCatalogEntry(StrictModel):
    case_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    category: str = Field(min_length=1)
    action_name: str = Field(min_length=1)
    decision: RecoveryFollowupDriverDecision
    verdict_status: VerificationStatus | None = None
    tags: list[str] = Field(default_factory=list)
    path: str = Field(min_length=1)
    summary: str = Field(min_length=1)


class RecoveryMemoryCaseCatalog(StrictModel):
    schema_version: MemoryCaseDocumentSchemaVersion = MemoryCaseDocumentSchemaVersion.V1
    catalog_dir: str = Field(min_length=1)
    entries: list[RecoveryMemoryCaseCatalogEntry] = Field(default_factory=list)
    summary: str = Field(min_length=1)


class MemoryCatalogRetrievalSchemaVersion(str, Enum):
    V1 = "v1"


class MemoryCatalogFilter(StrictModel):
    schema_version: MemoryCatalogRetrievalSchemaVersion = MemoryCatalogRetrievalSchemaVersion.V1
    case_ids: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    action_names: list[str] = Field(default_factory=list)
    decisions: list[RecoveryFollowupDriverDecision] = Field(default_factory=list)
    verdict_statuses: list[VerificationStatus] = Field(default_factory=list)
    tags_any: list[str] = Field(default_factory=list)
    tags_all: list[str] = Field(default_factory=list)


class MemoryCatalogRetrievalRequest(StrictModel):
    schema_version: MemoryCatalogRetrievalSchemaVersion = MemoryCatalogRetrievalSchemaVersion.V1
    query: RecoveryCaseQuery
    filters: MemoryCatalogFilter | None = None


class MemoryCatalogRetrievalResult(StrictModel):
    schema_version: MemoryCatalogRetrievalSchemaVersion = MemoryCatalogRetrievalSchemaVersion.V1
    catalog_dir: str = Field(min_length=1)
    catalog_case_count: int = Field(ge=0)
    filtered_case_count: int = Field(ge=0)
    matches: list[RecoveryCaseMatch] = Field(default_factory=list)
    applied_filters: MemoryCatalogFilter | None = None
    summary: str = Field(min_length=1)


class MemoryCasePersistenceService:
    def __init__(
        self,
        *,
        retrieval_service: MemoryCaseRetrievalService | None = None,
    ) -> None:
        self._retrieval_service = retrieval_service or MemoryCaseRetrievalService()

    def save_case(
        self,
        *,
        case: RecoveryMemoryCase,
        output_path: str,
    ) -> RecoveryMemoryCaseCatalogEntry:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        document = RecoveryMemoryCaseDocument(case=case)
        self._write_document(path=path, document=document)
        return self._build_catalog_entry(case=case, path=path)

    def load_case(self, path: str) -> RecoveryMemoryCase:
        return self._load_document(Path(path)).case

    def save_to_catalog(
        self,
        *,
        case: RecoveryMemoryCase,
        catalog_dir: str,
    ) -> RecoveryMemoryCaseCatalogEntry:
        path = self._catalog_path(Path(catalog_dir), case.case_id)
        return self.save_case(case=case, output_path=str(path))

    def list_catalog(self, catalog_dir: str) -> RecoveryMemoryCaseCatalog:
        directory = Path(catalog_dir)
        if not directory.exists():
            raise FileNotFoundError(f"Memory case catalog directory does not exist: {directory}")

        entries = [
            self._build_catalog_entry(case=document.case, path=path)
            for path, document in self._iter_catalog_documents(directory)
        ]
        entries.sort(key=lambda item: item.case_id)
        return RecoveryMemoryCaseCatalog(
            catalog_dir=str(directory),
            entries=entries,
            summary=f"Recovery memory case catalog {directory} contains {len(entries)} cases.",
        )

    def load_from_catalog(
        self,
        *,
        catalog_dir: str,
        case_id: str,
    ) -> RecoveryMemoryCase:
        return self.load_case(str(self._catalog_path(Path(catalog_dir), case_id)))

    def retrieve_from_catalog(
        self,
        *,
        catalog_dir: str,
        query: RecoveryCaseQuery,
    ) -> RecoveryCaseRetrievalResponse:
        directory = Path(catalog_dir)
        if not directory.exists():
            raise FileNotFoundError(f"Memory case catalog directory does not exist: {directory}")

        cases = [
            document.case
            for _, document in sorted(
                self._iter_catalog_documents(directory),
                key=lambda item: item[1].case.case_id,
            )
        ]
        return self._retrieval_service.retrieve(query=query, cases=cases)

    def _iter_catalog_documents(
        self,
        directory: Path,
    ) -> list[tuple[Path, RecoveryMemoryCaseDocument]]:
        documents: list[tuple[Path, RecoveryMemoryCaseDocument]] = []
        for path in sorted(directory.glob("*.json"), key=lambda item: item.name):
            documents.append((path, self._load_document(path)))
        return documents

    @staticmethod
    def _write_document(*, path: Path, document: RecoveryMemoryCaseDocument) -> None:
        payload = document.model_dump(mode="json")
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    @staticmethod
    def _load_document(path: Path) -> RecoveryMemoryCaseDocument:
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid memory case JSON document: {path}") from exc

        try:
            return RecoveryMemoryCaseDocument.model_validate(payload)
        except ValidationError as exc:
            raise ValueError(f"Invalid memory case document schema: {path}") from exc

    @staticmethod
    def _build_catalog_entry(
        *,
        case: RecoveryMemoryCase,
        path: Path,
    ) -> RecoveryMemoryCaseCatalogEntry:
        return RecoveryMemoryCaseCatalogEntry(
            case_id=case.case_id,
            source=case.source,
            category=case.category,
            action_name=case.action_name,
            decision=case.decision,
            verdict_status=case.verdict_status,
            tags=case.tags,
            path=str(path),
            summary=case.input_summary,
        )

    @staticmethod
    def _catalog_path(directory: Path, case_id: str) -> Path:
        encoded_case_id = quote(case_id, safe="-_")
        if len(encoded_case_id) > 120:
            digest = sha256(case_id.encode("utf-8")).hexdigest()
            encoded_case_id = f"memory-case-{digest}"
        return directory / f"{encoded_case_id}.json"


class MemoryCatalogRetrievalService:
    def __init__(
        self,
        *,
        persistence_service: MemoryCasePersistenceService | None = None,
        retrieval_service: MemoryCaseRetrievalService | None = None,
    ) -> None:
        self._persistence_service = persistence_service or MemoryCasePersistenceService()
        self._retrieval_service = retrieval_service or MemoryCaseRetrievalService()

    def preview_candidates(
        self,
        catalog_dir: str,
        filters: MemoryCatalogFilter | None = None,
    ) -> MemoryCatalogRetrievalResult:
        catalog = self._persistence_service.list_catalog(catalog_dir)
        cases = self._load_catalog_cases(catalog)
        filtered_cases = self._apply_filters(cases=cases, filters=filters)
        return MemoryCatalogRetrievalResult(
            catalog_dir=catalog.catalog_dir,
            catalog_case_count=len(cases),
            filtered_case_count=len(filtered_cases),
            matches=[],
            applied_filters=filters,
            summary=self._preview_summary(
                catalog_dir=catalog.catalog_dir,
                catalog_case_count=len(cases),
                filtered_case_count=len(filtered_cases),
            ),
        )

    def retrieve(
        self,
        catalog_dir: str,
        request: MemoryCatalogRetrievalRequest,
    ) -> MemoryCatalogRetrievalResult:
        catalog = self._persistence_service.list_catalog(catalog_dir)
        cases = self._load_catalog_cases(catalog)
        filtered_cases = self._apply_filters(cases=cases, filters=request.filters)
        retrieval_response = self._retrieval_service.retrieve(
            query=request.query,
            cases=filtered_cases,
        )
        return MemoryCatalogRetrievalResult(
            catalog_dir=catalog.catalog_dir,
            catalog_case_count=len(cases),
            filtered_case_count=len(filtered_cases),
            matches=retrieval_response.matches,
            applied_filters=request.filters,
            summary=self._retrieve_summary(
                catalog_dir=catalog.catalog_dir,
                catalog_case_count=len(cases),
                filtered_case_count=len(filtered_cases),
                query=request.query,
                retrieval_summary=retrieval_response.summary,
            ),
        )

    def _load_catalog_cases(self, catalog: RecoveryMemoryCaseCatalog) -> list[RecoveryMemoryCase]:
        cases = [self._persistence_service.load_case(entry.path) for entry in catalog.entries]
        return sorted(cases, key=lambda item: item.case_id)

    @classmethod
    def _apply_filters(
        cls,
        *,
        cases: list[RecoveryMemoryCase],
        filters: MemoryCatalogFilter | None,
    ) -> list[RecoveryMemoryCase]:
        if filters is None:
            return cases

        case_ids = set(cls._normalize_strings(filters.case_ids))
        sources = set(cls._normalize_strings(filters.sources))
        categories = set(cls._normalize_strings(filters.categories))
        action_names = set(cls._normalize_strings(filters.action_names))
        decisions = set(filters.decisions)
        verdict_statuses = set(filters.verdict_statuses)
        tags_any = set(cls._normalize_strings(filters.tags_any))
        tags_all = set(cls._normalize_strings(filters.tags_all))

        filtered: list[RecoveryMemoryCase] = []
        for case in cases:
            case_tags = set(case.tags)
            if case_ids and case.case_id not in case_ids:
                continue
            if sources and case.source not in sources:
                continue
            if categories and case.category not in categories:
                continue
            if action_names and case.action_name not in action_names:
                continue
            if decisions and case.decision not in decisions:
                continue
            if verdict_statuses and case.verdict_status not in verdict_statuses:
                continue
            if tags_any and not case_tags.intersection(tags_any):
                continue
            if tags_all and not tags_all.issubset(case_tags):
                continue
            filtered.append(case)
        return filtered

    @staticmethod
    def _normalize_strings(values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw_value in values:
            value = raw_value.strip()
            if not value or value in seen:
                continue
            seen.add(value)
            normalized.append(value)
        return normalized

    @staticmethod
    def _preview_summary(
        *,
        catalog_dir: str,
        catalog_case_count: int,
        filtered_case_count: int,
    ) -> str:
        if catalog_case_count == 0:
            return f"Memory catalog {catalog_dir} has no candidate evidence."
        return (
            f"Memory catalog {catalog_dir} has {catalog_case_count} cases; "
            f"{filtered_case_count} candidates remain after filters."
        )

    @staticmethod
    def _retrieve_summary(
        *,
        catalog_dir: str,
        catalog_case_count: int,
        filtered_case_count: int,
        query: RecoveryCaseQuery,
        retrieval_summary: str,
    ) -> str:
        if catalog_case_count == 0:
            return f"Memory catalog {catalog_dir} has no candidate evidence. {retrieval_summary}"
        if not any((query.category, query.action_name, query.decision, query.verdict_status, query.tags)):
            return (
                f"Memory catalog {catalog_dir} filtered {filtered_case_count} of "
                f"{catalog_case_count} cases, but retrieval requires at least one query filter."
            )
        return (
            f"Memory catalog {catalog_dir} filtered {filtered_case_count} of "
            f"{catalog_case_count} cases. {retrieval_summary}"
        )
