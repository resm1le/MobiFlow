from __future__ import annotations

"""Memory vector adapter assets and service."""

from enum import Enum

from pydantic import Field

from mobiflow_agent.common.contracts import StrictModel, VerificationStatus
from mobiflow_agent.memory.quality import MemoryCaseQualityDecision
from mobiflow_agent.execution.followup.driver import RecoveryFollowupDriverDecision

class MemoryVectorAdapterSchemaVersion(str, Enum):
    V1 = "v1"

class MemoryVectorRecord(StrictModel):
    schema_version: MemoryVectorAdapterSchemaVersion = MemoryVectorAdapterSchemaVersion.V1
    case_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    category: str = Field(min_length=1)
    action_name: str = Field(min_length=1)
    decision: RecoveryFollowupDriverDecision
    verdict_status: VerificationStatus | None = None
    tags: list[str] = Field(default_factory=list)
    quality_decision: MemoryCaseQualityDecision
    quality_issue_count: int = Field(ge=0)
    embedding_text: str = Field(min_length=1)
    summary: str = Field(min_length=1)

class MemoryVectorUpsertResult(StrictModel):
    schema_version: MemoryVectorAdapterSchemaVersion = MemoryVectorAdapterSchemaVersion.V1
    case_id: str = Field(min_length=1)
    replaced_existing: bool = False
    record_count: int = Field(ge=0)
    summary: str = Field(min_length=1)

class MemoryVectorQueryRequest(StrictModel):
    schema_version: MemoryVectorAdapterSchemaVersion = MemoryVectorAdapterSchemaVersion.V1
    query_text: str = ""
    limit: int = Field(default=5, ge=1)

class MemoryVectorQueryMatch(StrictModel):
    record: MemoryVectorRecord
    score: int = Field(ge=0)
    matched_terms: list[str] = Field(default_factory=list)
    summary: str = Field(min_length=1)

class MemoryVectorQueryResult(StrictModel):
    schema_version: MemoryVectorAdapterSchemaVersion = MemoryVectorAdapterSchemaVersion.V1
    query: MemoryVectorQueryRequest
    indexed_record_count: int = Field(ge=0)
    matches: list[MemoryVectorQueryMatch] = Field(default_factory=list)
    summary: str = Field(min_length=1)

class MemoryVectorCatalogIndexResult(StrictModel):
    schema_version: MemoryVectorAdapterSchemaVersion = MemoryVectorAdapterSchemaVersion.V1
    catalog_dir: str = Field(min_length=1)
    catalog_asset_count: int = Field(ge=0)
    indexed_records: int = Field(ge=0)
    skipped_records: int = Field(ge=0)
    upserts: list[MemoryVectorUpsertResult] = Field(default_factory=list)
    summary: str = Field(min_length=1)

import re

from mobiflow_agent.memory.embedding import RecoveryMemoryEmbeddingAsset
from mobiflow_agent.memory.embedding import MemoryEmbeddingAssetService
class MemoryVectorAdapterService:
    def __init__(
        self,
        *,
        embedding_service: MemoryEmbeddingAssetService | None = None,
    ) -> None:
        self._embedding_service = embedding_service or MemoryEmbeddingAssetService()
        self._records: dict[str, MemoryVectorRecord] = {}

    def upsert_asset(self, asset: RecoveryMemoryEmbeddingAsset) -> MemoryVectorUpsertResult:
        record = self._record_from_asset(asset)
        replaced_existing = asset.case_id in self._records
        self._records[asset.case_id] = record
        record_count = len(self._records)
        action = "Updated" if replaced_existing else "Indexed"
        return MemoryVectorUpsertResult(
            case_id=asset.case_id,
            replaced_existing=replaced_existing,
            record_count=record_count,
            summary=f"{action} memory vector record {asset.case_id}; index now contains {record_count} record(s).",
        )

    def upsert_catalog(self, catalog_dir: str) -> MemoryVectorCatalogIndexResult:
        catalog = self._embedding_service.list_catalog(catalog_dir)
        upserts: list[MemoryVectorUpsertResult] = []
        for entry in catalog.entries:
            asset = self._embedding_service.load_from_catalog(
                catalog_dir=catalog.catalog_dir,
                case_id=entry.case_id,
            )
            upserts.append(self.upsert_asset(asset))

        indexed_records = len(upserts)
        return MemoryVectorCatalogIndexResult(
            catalog_dir=catalog.catalog_dir,
            catalog_asset_count=len(catalog.entries),
            indexed_records=indexed_records,
            skipped_records=0,
            upserts=upserts,
            summary=(
                f"Indexed {indexed_records} embedding asset(s) from catalog {catalog.catalog_dir}; "
                f"in-memory vector index now contains {len(self._records)} record(s)."
            ),
        )

    def get_record(self, case_id: str) -> MemoryVectorRecord | None:
        record = self._records.get(case_id)
        return record.model_copy(deep=True) if record is not None else None

    def query(self, request: MemoryVectorQueryRequest) -> MemoryVectorQueryResult:
        indexed_record_count = len(self._records)
        normalized_query = request.query_text.strip()
        if not normalized_query:
            return MemoryVectorQueryResult(
                query=request,
                indexed_record_count=indexed_record_count,
                matches=[],
                summary="Memory vector query requires non-empty query_text.",
            )

        if not self._records:
            return MemoryVectorQueryResult(
                query=request,
                indexed_record_count=0,
                matches=[],
                summary="Memory vector adapter has no indexed records.",
            )

        query_terms = self._tokenize(normalized_query)
        scored_matches: list[MemoryVectorQueryMatch] = []
        for record in self._records.values():
            record_terms = set(self._tokenize(record.embedding_text))
            matched_terms = [term for term in query_terms if term in record_terms]
            score = len(matched_terms)
            if score == 0:
                continue
            scored_matches.append(
                MemoryVectorQueryMatch(
                    record=record.model_copy(deep=True),
                    score=score,
                    matched_terms=matched_terms,
                    summary=f"Matched vector terms: {', '.join(matched_terms)} (score={score}).",
                )
            )

        ordered_matches = sorted(
            scored_matches,
            key=lambda match: (-match.score, match.record.case_id),
        )
        limited_matches = ordered_matches[: request.limit]
        summary = (
            f"Retrieved {len(limited_matches)} memory vector match(es) from {indexed_record_count} indexed record(s)."
            if limited_matches
            else f"No memory vector records matched query_text across {indexed_record_count} indexed record(s)."
        )
        return MemoryVectorQueryResult(
            query=request,
            indexed_record_count=indexed_record_count,
            matches=limited_matches,
            summary=summary,
        )

    def clear(self) -> None:
        self._records.clear()

    @staticmethod
    def _record_from_asset(asset: RecoveryMemoryEmbeddingAsset) -> MemoryVectorRecord:
        return MemoryVectorRecord(
            case_id=asset.case_id,
            source=asset.source,
            category=asset.category,
            action_name=asset.action_name,
            decision=asset.decision,
            verdict_status=asset.verdict_status,
            tags=list(asset.tags),
            quality_decision=asset.quality_decision,
            quality_issue_count=asset.quality_issue_count,
            embedding_text=asset.embedding_text,
            summary=asset.summary,
        )

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        normalized = text.strip().lower()
        if not normalized:
            return []
        terms: list[str] = []
        seen: set[str] = set()
        for term in re.findall(r"[a-z0-9_]+", normalized):
            if term in seen:
                continue
            seen.add(term)
            terms.append(term)
        return terms
