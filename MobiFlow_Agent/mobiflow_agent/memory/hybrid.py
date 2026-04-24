from __future__ import annotations

"""Memory hybrid retrieval assets and service."""

from enum import Enum

from pydantic import Field

from mobiflow_agent.common.contracts import StrictModel
from mobiflow_agent.memory.case import RecoveryCaseQuery, RecoveryMemoryCase
from mobiflow_agent.memory.catalog import MemoryCatalogFilter

class MemoryHybridRetrievalSchemaVersion(str, Enum):
    V1 = "v1"

class MemoryHybridRetrievalRequest(StrictModel):
    schema_version: MemoryHybridRetrievalSchemaVersion = MemoryHybridRetrievalSchemaVersion.V1
    query: RecoveryCaseQuery
    vector_query_text: str | None = None
    filters: MemoryCatalogFilter | None = None
    limit: int = Field(default=5, ge=1)
    prefer_vector: bool = False

class MemoryHybridRetrievalMatch(StrictModel):
    case: RecoveryMemoryCase
    combined_score: int = Field(ge=0)
    deterministic_score: int = Field(ge=0)
    vector_score: int = Field(ge=0)
    match_sources: list[str] = Field(default_factory=list)
    summary: str = Field(min_length=1)

class MemoryHybridRetrievalResult(StrictModel):
    schema_version: MemoryHybridRetrievalSchemaVersion = MemoryHybridRetrievalSchemaVersion.V1
    catalog_dir: str = Field(min_length=1)
    catalog_case_count: int = Field(ge=0)
    filtered_case_count: int = Field(ge=0)
    request: MemoryHybridRetrievalRequest
    matches: list[MemoryHybridRetrievalMatch] = Field(default_factory=list)
    summary: str = Field(min_length=1)

from mobiflow_agent.memory.case import RecoveryCaseQuery, RecoveryMemoryCase
from mobiflow_agent.memory.catalog import MemoryCasePersistenceService
from mobiflow_agent.memory.catalog import MemoryCatalogFilter, MemoryCatalogRetrievalResult
from mobiflow_agent.memory.catalog import MemoryCatalogRetrievalService
from mobiflow_agent.memory.vector import MemoryVectorQueryRequest
from mobiflow_agent.memory.vector import MemoryVectorAdapterService

class MemoryHybridRetrievalService:
    def __init__(
        self,
        *,
        persistence_service: MemoryCasePersistenceService | None = None,
        catalog_retrieval_service: MemoryCatalogRetrievalService | None = None,
        vector_adapter_service: MemoryVectorAdapterService | None = None,
    ) -> None:
        self._persistence_service = persistence_service or MemoryCasePersistenceService()
        self._catalog_retrieval_service = catalog_retrieval_service or MemoryCatalogRetrievalService(
            persistence_service=self._persistence_service
        )
        self._vector_adapter_service = vector_adapter_service or MemoryVectorAdapterService()

    def preview_candidates(
        self,
        catalog_dir: str,
        filters: MemoryCatalogFilter | None = None,
    ) -> MemoryCatalogRetrievalResult:
        return self._catalog_retrieval_service.preview_candidates(catalog_dir, filters)

    def retrieve(
        self,
        catalog_dir: str,
        request: MemoryHybridRetrievalRequest,
    ) -> MemoryHybridRetrievalResult:
        catalog = self._persistence_service.list_catalog(catalog_dir)
        cases = self._load_catalog_cases(catalog.catalog_dir)
        filtered_cases = MemoryCatalogRetrievalService._apply_filters(cases=cases, filters=request.filters)
        deterministic_query = self._resolved_query(request)

        deterministic_input = self._has_deterministic_input(deterministic_query)
        vector_input = bool(request.vector_query_text and request.vector_query_text.strip())

        deterministic_matches = []
        deterministic_summary = ""
        if deterministic_input:
            deterministic_result = self._catalog_retrieval_service.retrieve(
                catalog.catalog_dir,
                request=self._catalog_request(query=deterministic_query, filters=request.filters),
            )
            deterministic_matches = deterministic_result.matches
            deterministic_summary = deterministic_result.summary

        vector_matches = []
        vector_summary = ""
        if vector_input:
            vector_result = self._vector_adapter_service.query(
                MemoryVectorQueryRequest(
                    query_text=request.vector_query_text or "",
                    limit=2_147_483_647,
                )
            )
            candidate_ids = {case.case_id for case in filtered_cases}
            vector_matches = [
                match
                for match in vector_result.matches
                if match.record.case_id in candidate_ids
            ]
            vector_summary = vector_result.summary

        if not deterministic_input and not vector_input:
            return MemoryHybridRetrievalResult(
                catalog_dir=catalog.catalog_dir,
                catalog_case_count=len(cases),
                filtered_case_count=len(filtered_cases),
                request=request,
                matches=[],
                summary=(
                    f"Memory catalog {catalog.catalog_dir} filtered {len(filtered_cases)} of "
                    f"{len(cases)} cases, but hybrid retrieval requires deterministic query filters "
                    f"or vector_query_text."
                ),
            )

        merged_matches = self._merge_matches(
            filtered_cases=filtered_cases,
            deterministic_matches=deterministic_matches,
            vector_matches=vector_matches,
            prefer_vector=request.prefer_vector,
        )[: request.limit]

        return MemoryHybridRetrievalResult(
            catalog_dir=catalog.catalog_dir,
            catalog_case_count=len(cases),
            filtered_case_count=len(filtered_cases),
            request=request,
            matches=merged_matches,
            summary=self._summary(
                catalog_dir=catalog.catalog_dir,
                catalog_case_count=len(cases),
                filtered_case_count=len(filtered_cases),
                match_count=len(merged_matches),
                deterministic_input=deterministic_input,
                vector_input=vector_input,
                deterministic_summary=deterministic_summary,
                vector_summary=vector_summary,
            ),
        )

    def _load_catalog_cases(self, catalog_dir: str) -> list[RecoveryMemoryCase]:
        catalog = self._persistence_service.list_catalog(catalog_dir)
        cases = [self._persistence_service.load_case(entry.path) for entry in catalog.entries]
        return sorted(cases, key=lambda item: item.case_id)

    @staticmethod
    def _resolved_query(request: MemoryHybridRetrievalRequest) -> RecoveryCaseQuery:
        return request.query.model_copy(update={"limit": request.limit})

    @staticmethod
    def _has_deterministic_input(query: RecoveryCaseQuery) -> bool:
        return any((query.category, query.action_name, query.decision, query.verdict_status, query.tags))

    @staticmethod
    def _catalog_request(
        *,
        query: RecoveryCaseQuery,
        filters: MemoryCatalogFilter | None,
    ):
        from mobiflow_agent.memory.catalog import MemoryCatalogRetrievalRequest

        return MemoryCatalogRetrievalRequest(query=query, filters=filters)

    @classmethod
    def _merge_matches(
        cls,
        *,
        filtered_cases: list[RecoveryMemoryCase],
        deterministic_matches,
        vector_matches,
        prefer_vector: bool,
    ) -> list[MemoryHybridRetrievalMatch]:
        case_by_id = {case.case_id: case for case in filtered_cases}
        deterministic_by_id = {match.case.case_id: match for match in deterministic_matches}
        vector_by_id = {match.record.case_id: match for match in vector_matches}

        merged: list[MemoryHybridRetrievalMatch] = []
        for case_id in sorted(set(deterministic_by_id) | set(vector_by_id)):
            case = case_by_id.get(case_id)
            if case is None:
                continue

            deterministic_match = deterministic_by_id.get(case_id)
            vector_match = vector_by_id.get(case_id)
            deterministic_score = deterministic_match.score if deterministic_match is not None else 0
            vector_score = vector_match.score if vector_match is not None else 0
            combined_score = deterministic_score + vector_score
            match_sources: list[str] = []
            summary_parts: list[str] = []

            if deterministic_match is not None:
                match_sources.append("deterministic")
                summary_parts.append(deterministic_match.summary)
            if vector_match is not None:
                match_sources.append("vector")
                summary_parts.append(vector_match.summary)

            merged.append(
                MemoryHybridRetrievalMatch(
                    case=case,
                    combined_score=combined_score,
                    deterministic_score=deterministic_score,
                    vector_score=vector_score,
                    match_sources=match_sources,
                    summary=cls._match_summary(
                        match_sources=match_sources,
                        combined_score=combined_score,
                        deterministic_score=deterministic_score,
                        vector_score=vector_score,
                        detail_parts=summary_parts,
                    ),
                )
            )

        sort_key = cls._vector_preferred_sort_key if prefer_vector else cls._deterministic_preferred_sort_key
        return sorted(merged, key=sort_key)

    @staticmethod
    def _match_summary(
        *,
        match_sources: list[str],
        combined_score: int,
        deterministic_score: int,
        vector_score: int,
        detail_parts: list[str],
    ) -> str:
        sources = " + ".join(match_sources)
        return (
            f"Matched via {sources} (combined_score={combined_score}, "
            f"deterministic_score={deterministic_score}, vector_score={vector_score}). "
            + " ".join(detail_parts)
        )

    @staticmethod
    def _deterministic_preferred_sort_key(match: MemoryHybridRetrievalMatch) -> tuple[int, int, int, str]:
        return (
            -match.combined_score,
            -match.deterministic_score,
            -match.vector_score,
            match.case.case_id,
        )

    @staticmethod
    def _vector_preferred_sort_key(match: MemoryHybridRetrievalMatch) -> tuple[int, int, int, str]:
        return (
            -match.combined_score,
            -match.vector_score,
            -match.deterministic_score,
            match.case.case_id,
        )

    @staticmethod
    def _summary(
        *,
        catalog_dir: str,
        catalog_case_count: int,
        filtered_case_count: int,
        match_count: int,
        deterministic_input: bool,
        vector_input: bool,
        deterministic_summary: str,
        vector_summary: str,
    ) -> str:
        if catalog_case_count == 0:
            return f"Memory catalog {catalog_dir} has no candidate evidence."

        if match_count > 0:
            return (
                f"Memory catalog {catalog_dir} filtered {filtered_case_count} of {catalog_case_count} cases. "
                f"Retrieved {match_count} hybrid memory case(s)."
            )

        if deterministic_input and not vector_input:
            return (
                f"Memory catalog {catalog_dir} filtered {filtered_case_count} of {catalog_case_count} cases. "
                f"{deterministic_summary}"
            )
        if vector_input and not deterministic_input:
            return (
                f"Memory catalog {catalog_dir} filtered {filtered_case_count} of {catalog_case_count} cases. "
                "No hybrid memory cases matched the vector query."
            )
        return (
            f"Memory catalog {catalog_dir} filtered {filtered_case_count} of {catalog_case_count} cases. "
            "No hybrid memory cases matched the deterministic/vector request."
        ).strip()
