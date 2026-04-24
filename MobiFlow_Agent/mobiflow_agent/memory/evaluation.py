from __future__ import annotations

"""Memory retrieval evaluation assets and service."""

import json
from enum import Enum
from hashlib import sha256
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

from pydantic import Field, ValidationError

from mobiflow_agent.common.contracts import StrictModel
from mobiflow_agent.memory.case import RecoveryCaseQuery
from mobiflow_agent.memory.catalog import (
    MemoryCatalogFilter,
    MemoryCatalogRetrievalRequest,
    MemoryCatalogRetrievalService,
    MemoryCasePersistenceService,
)
from mobiflow_agent.memory.hybrid import (
    MemoryHybridRetrievalRequest,
    MemoryHybridRetrievalService,
)
from mobiflow_agent.memory.vector import (
    MemoryVectorAdapterService,
    MemoryVectorQueryRequest,
)
from mobiflow_agent.memory.models import (
    TaskMemoryQuery,
    TaskMemoryRetrievalChannel,
    TaskMemoryRetrievalResult,
)
from mobiflow_agent.memory.retrieval import TaskMemoryRetrievalService
from mobiflow_agent.memory.runtime import TaskMemoryRuntime
from mobiflow_agent.memory.store import TaskMemoryStore


class MemoryRetrievalEvaluationSchemaVersion(str, Enum):
    V1 = "v1"


class MemoryRetrievalEvaluationChannel(str, Enum):
    DETERMINISTIC = "deterministic"
    VECTOR = "vector"
    HYBRID = "hybrid"


class MemoryRetrievalEvaluationDecision(str, Enum):
    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"


class MemoryRetrievalEvaluationCase(StrictModel):
    schema_version: MemoryRetrievalEvaluationSchemaVersion = (
        MemoryRetrievalEvaluationSchemaVersion.V1
    )
    evaluation_case_id: str = Field(min_length=1)
    query: RecoveryCaseQuery
    vector_query_text: str | None = None
    filters: MemoryCatalogFilter | None = None
    expected_case_ids: list[str] = Field(default_factory=list)
    limit: int = Field(default=5, ge=1)
    summary: str = Field(min_length=1)


class MemoryRetrievalEvaluationChannelResult(StrictModel):
    schema_version: MemoryRetrievalEvaluationSchemaVersion = (
        MemoryRetrievalEvaluationSchemaVersion.V1
    )
    evaluation_case_id: str = Field(min_length=1)
    channel: MemoryRetrievalEvaluationChannel
    decision: MemoryRetrievalEvaluationDecision
    matched_expected_case_ids: list[str] = Field(default_factory=list)
    missed_expected_case_ids: list[str] = Field(default_factory=list)
    unexpected_case_ids: list[str] = Field(default_factory=list)
    top_case_ids: list[str] = Field(default_factory=list)
    match_count: int = Field(ge=0)
    hit_count: int = Field(ge=0)
    top_hit: bool
    summary: str = Field(min_length=1)


class MemoryRetrievalEvaluationResult(StrictModel):
    schema_version: MemoryRetrievalEvaluationSchemaVersion = (
        MemoryRetrievalEvaluationSchemaVersion.V1
    )
    evaluation_id: str = Field(min_length=1)
    catalog_dir: str = Field(min_length=1)
    embedding_catalog_dir: str | None = None
    evaluated_cases: int = Field(ge=0)
    passed_channels: int = Field(ge=0)
    warning_channels: int = Field(ge=0)
    failed_channels: int = Field(ge=0)
    results: list[MemoryRetrievalEvaluationChannelResult] = Field(default_factory=list)
    summary: str = Field(min_length=1)


class MemoryRetrievalEvaluationDocument(StrictModel):
    schema_version: MemoryRetrievalEvaluationSchemaVersion = (
        MemoryRetrievalEvaluationSchemaVersion.V1
    )
    evaluation: MemoryRetrievalEvaluationResult


class MemoryRetrievalEvaluationCatalogEntry(StrictModel):
    evaluation_id: str = Field(min_length=1)
    evaluated_cases: int = Field(ge=0)
    passed_channels: int = Field(ge=0)
    warning_channels: int = Field(ge=0)
    failed_channels: int = Field(ge=0)
    path: str = Field(min_length=1)
    summary: str = Field(min_length=1)


class MemoryRetrievalEvaluationCatalog(StrictModel):
    schema_version: MemoryRetrievalEvaluationSchemaVersion = (
        MemoryRetrievalEvaluationSchemaVersion.V1
    )
    catalog_dir: str = Field(min_length=1)
    entries: list[MemoryRetrievalEvaluationCatalogEntry] = Field(default_factory=list)
    summary: str = Field(min_length=1)


def build_memory_retrieval_evaluation_id() -> str:
    return f"memory-retrieval-evaluation:{uuid4().hex}"


class MemoryRetrievalEvaluationService:
    def __init__(
        self,
        *,
        persistence_service: MemoryCasePersistenceService | None = None,
        catalog_retrieval_service: MemoryCatalogRetrievalService | None = None,
    ) -> None:
        self._persistence_service = persistence_service or MemoryCasePersistenceService()
        self._catalog_retrieval_service = catalog_retrieval_service or MemoryCatalogRetrievalService(
            persistence_service=self._persistence_service
        )

    def evaluate_case(
        self,
        catalog_dir: str,
        evaluation_case: MemoryRetrievalEvaluationCase,
        *,
        embedding_catalog_dir: str | None = None,
        prefer_vector: bool = False,
    ) -> MemoryRetrievalEvaluationResult:
        return self.evaluate_cases(
            catalog_dir,
            [evaluation_case],
            embedding_catalog_dir=embedding_catalog_dir,
            prefer_vector=prefer_vector,
        )

    def evaluate_cases(
        self,
        catalog_dir: str,
        evaluation_cases: list[MemoryRetrievalEvaluationCase],
        *,
        embedding_catalog_dir: str | None = None,
        prefer_vector: bool = False,
        evaluation_id: str | None = None,
    ) -> MemoryRetrievalEvaluationResult:
        catalog = self._persistence_service.list_catalog(catalog_dir)
        vector_adapter = self._prepare_vector_adapter(embedding_catalog_dir)
        hybrid_service = MemoryHybridRetrievalService(
            persistence_service=self._persistence_service,
            catalog_retrieval_service=self._catalog_retrieval_service,
            vector_adapter_service=vector_adapter,
        )

        all_results: list[MemoryRetrievalEvaluationChannelResult] = []
        no_vector_evidence = False

        for evaluation_case in evaluation_cases:
            self._validate_evaluation_case(evaluation_case)

            if not catalog.entries:
                all_results.extend(self._no_candidate_evidence_results(evaluation_case))
                continue

            deterministic_result = self._catalog_retrieval_service.retrieve(
                catalog.catalog_dir,
                MemoryCatalogRetrievalRequest(
                    query=evaluation_case.query.model_copy(update={"limit": evaluation_case.limit}),
                    filters=evaluation_case.filters,
                ),
            )
            vector_result = vector_adapter.query(
                MemoryVectorQueryRequest(
                    query_text=evaluation_case.vector_query_text or "",
                    limit=evaluation_case.limit,
                )
            )
            if "no indexed records" in vector_result.summary:
                no_vector_evidence = True

            hybrid_result = hybrid_service.retrieve(
                catalog.catalog_dir,
                MemoryHybridRetrievalRequest(
                    query=evaluation_case.query,
                    vector_query_text=evaluation_case.vector_query_text,
                    filters=evaluation_case.filters,
                    limit=evaluation_case.limit,
                    prefer_vector=prefer_vector,
                ),
            )

            all_results.extend(
                [
                    self._evaluate_channel(
                        evaluation_case=evaluation_case,
                        channel=MemoryRetrievalEvaluationChannel.DETERMINISTIC,
                        top_case_ids=[match.case.case_id for match in deterministic_result.matches],
                        raw_summary=deterministic_result.summary,
                    ),
                    self._evaluate_channel(
                        evaluation_case=evaluation_case,
                        channel=MemoryRetrievalEvaluationChannel.VECTOR,
                        top_case_ids=[match.record.case_id for match in vector_result.matches],
                        raw_summary=vector_result.summary,
                    ),
                    self._evaluate_channel(
                        evaluation_case=evaluation_case,
                        channel=MemoryRetrievalEvaluationChannel.HYBRID,
                        top_case_ids=[match.case.case_id for match in hybrid_result.matches],
                        raw_summary=hybrid_result.summary,
                    ),
                ]
            )

        passed_channels = sum(
            1
            for result in all_results
            if result.decision == MemoryRetrievalEvaluationDecision.PASSED
        )
        warning_channels = sum(
            1
            for result in all_results
            if result.decision == MemoryRetrievalEvaluationDecision.WARNING
        )
        failed_channels = sum(
            1
            for result in all_results
            if result.decision == MemoryRetrievalEvaluationDecision.FAILED
        )

        result = MemoryRetrievalEvaluationResult(
            evaluation_id=evaluation_id or build_memory_retrieval_evaluation_id(),
            catalog_dir=catalog.catalog_dir,
            embedding_catalog_dir=embedding_catalog_dir,
            evaluated_cases=len(evaluation_cases),
            passed_channels=passed_channels,
            warning_channels=warning_channels,
            failed_channels=failed_channels,
            results=all_results,
            summary=self._result_summary(
                evaluated_cases=len(evaluation_cases),
                passed_channels=passed_channels,
                warning_channels=warning_channels,
                failed_channels=failed_channels,
                catalog_dir=catalog.catalog_dir,
                no_vector_evidence=no_vector_evidence,
            ),
        )
        return result

    def save_result(
        self,
        result: MemoryRetrievalEvaluationResult,
        output_path: str,
    ) -> MemoryRetrievalEvaluationCatalogEntry:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        document = MemoryRetrievalEvaluationDocument(evaluation=result)
        payload = document.model_dump(mode="json")
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return self._build_catalog_entry(result=result, path=path)

    def load_result(self, path: str) -> MemoryRetrievalEvaluationResult:
        return self._load_document(Path(path)).evaluation

    def save_to_catalog(
        self,
        result: MemoryRetrievalEvaluationResult,
        catalog_dir: str,
    ) -> MemoryRetrievalEvaluationCatalogEntry:
        path = self._catalog_path(Path(catalog_dir), result.evaluation_id)
        return self.save_result(result, str(path))

    def list_catalog(self, catalog_dir: str) -> MemoryRetrievalEvaluationCatalog:
        directory = Path(catalog_dir)
        if not directory.exists():
            raise FileNotFoundError(
                f"Memory retrieval evaluation catalog directory does not exist: {directory}"
            )

        entries = [
            self._build_catalog_entry(result=document.evaluation, path=path)
            for path, document in self._iter_catalog_documents(directory)
        ]
        entries.sort(key=lambda item: item.evaluation_id)
        return MemoryRetrievalEvaluationCatalog(
            catalog_dir=str(directory),
            entries=entries,
            summary=(
                f"Memory retrieval evaluation catalog {directory} contains "
                f"{len(entries)} evaluation document(s)."
            ),
        )

    def _prepare_vector_adapter(
        self,
        embedding_catalog_dir: str | None,
    ) -> MemoryVectorAdapterService:
        adapter = MemoryVectorAdapterService()
        if embedding_catalog_dir is not None:
            adapter.upsert_catalog(embedding_catalog_dir)
        return adapter

    @staticmethod
    def _validate_evaluation_case(evaluation_case: MemoryRetrievalEvaluationCase) -> None:
        if not evaluation_case.expected_case_ids:
            raise ValueError(
                "Memory retrieval evaluation requires at least one expected_case_id."
            )

    @classmethod
    def _evaluate_channel(
        cls,
        *,
        evaluation_case: MemoryRetrievalEvaluationCase,
        channel: MemoryRetrievalEvaluationChannel,
        top_case_ids: list[str],
        raw_summary: str,
    ) -> MemoryRetrievalEvaluationChannelResult:
        expected_ids = list(dict.fromkeys(evaluation_case.expected_case_ids))
        matched_expected = [case_id for case_id in top_case_ids if case_id in expected_ids]
        missed_expected = [case_id for case_id in expected_ids if case_id not in matched_expected]
        unexpected = [case_id for case_id in top_case_ids if case_id not in expected_ids]
        top_hit = bool(top_case_ids) and top_case_ids[0] in expected_ids

        if matched_expected:
            decision = MemoryRetrievalEvaluationDecision.PASSED
        else:
            decision = MemoryRetrievalEvaluationDecision.FAILED

        summary = cls._channel_summary(
            evaluation_case_id=evaluation_case.evaluation_case_id,
            channel=channel,
            decision=decision,
            top_case_ids=top_case_ids,
            matched_expected=matched_expected,
            unexpected=unexpected,
            raw_summary=raw_summary,
        )
        return MemoryRetrievalEvaluationChannelResult(
            evaluation_case_id=evaluation_case.evaluation_case_id,
            channel=channel,
            decision=decision,
            matched_expected_case_ids=matched_expected,
            missed_expected_case_ids=missed_expected,
            unexpected_case_ids=unexpected,
            top_case_ids=top_case_ids,
            match_count=len(top_case_ids),
            hit_count=len(matched_expected),
            top_hit=top_hit,
            summary=summary,
        )

    @classmethod
    def _no_candidate_evidence_results(
        cls,
        evaluation_case: MemoryRetrievalEvaluationCase,
    ) -> list[MemoryRetrievalEvaluationChannelResult]:
        summary = "Memory catalog has no candidate evidence for retrieval evaluation."
        return [
            cls._evaluate_channel(
                evaluation_case=evaluation_case,
                channel=channel,
                top_case_ids=[],
                raw_summary=summary,
            )
            for channel in (
                MemoryRetrievalEvaluationChannel.DETERMINISTIC,
                MemoryRetrievalEvaluationChannel.VECTOR,
                MemoryRetrievalEvaluationChannel.HYBRID,
            )
        ]

    @staticmethod
    def _channel_summary(
        *,
        evaluation_case_id: str,
        channel: MemoryRetrievalEvaluationChannel,
        decision: MemoryRetrievalEvaluationDecision,
        top_case_ids: list[str],
        matched_expected: list[str],
        unexpected: list[str],
        raw_summary: str,
    ) -> str:
        if not top_case_ids:
            return (
                f"Evaluation case {evaluation_case_id} channel {channel.value} "
                f"failed with no retrieval evidence. {raw_summary}"
            )

        details: list[str] = [
            f"Evaluation case {evaluation_case_id} channel {channel.value} {decision.value}.",
            f"top_case_ids={top_case_ids}.",
        ]
        if matched_expected:
            details.append(f"matched_expected_case_ids={matched_expected}.")
        if unexpected:
            details.append(f"unexpected_case_ids={unexpected}.")
        details.append(raw_summary)
        return " ".join(details)

    @staticmethod
    def _result_summary(
        *,
        evaluated_cases: int,
        passed_channels: int,
        warning_channels: int,
        failed_channels: int,
        catalog_dir: str,
        no_vector_evidence: bool,
    ) -> str:
        summary = (
            f"Evaluated {evaluated_cases} memory retrieval case(s) against catalog {catalog_dir}; "
            f"passed_channels={passed_channels}, warning_channels={warning_channels}, "
            f"failed_channels={failed_channels}."
        )
        if no_vector_evidence:
            summary += " Some vector evaluations had no indexed vector records."
        return summary

    def _iter_catalog_documents(
        self,
        directory: Path,
    ) -> list[tuple[Path, MemoryRetrievalEvaluationDocument]]:
        documents: list[tuple[Path, MemoryRetrievalEvaluationDocument]] = []
        for path in sorted(directory.glob("*.json"), key=lambda item: item.name):
            documents.append((path, self._load_document(path)))
        return documents

    @staticmethod
    def _load_document(path: Path) -> MemoryRetrievalEvaluationDocument:
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid memory retrieval evaluation JSON document: {path}") from exc
        try:
            return MemoryRetrievalEvaluationDocument.model_validate(payload)
        except ValidationError as exc:
            raise ValueError(
                f"Invalid memory retrieval evaluation document schema: {path}"
            ) from exc

    @staticmethod
    def _build_catalog_entry(
        *,
        result: MemoryRetrievalEvaluationResult,
        path: Path,
    ) -> MemoryRetrievalEvaluationCatalogEntry:
        return MemoryRetrievalEvaluationCatalogEntry(
            evaluation_id=result.evaluation_id,
            evaluated_cases=result.evaluated_cases,
            passed_channels=result.passed_channels,
            warning_channels=result.warning_channels,
            failed_channels=result.failed_channels,
            path=str(path),
            summary=result.summary,
        )

    @staticmethod
    def _catalog_path(directory: Path, evaluation_id: str) -> Path:
        encoded_evaluation_id = quote(evaluation_id, safe="-_")
        if len(encoded_evaluation_id) > 120:
            digest = sha256(evaluation_id.encode("utf-8")).hexdigest()
            encoded_evaluation_id = f"memory-retrieval-evaluation-{digest}"
        return directory / f"{encoded_evaluation_id}.json"


class TaskMemoryEvaluationCase(StrictModel):
    evaluation_case_id: str = Field(min_length=1)
    query: TaskMemoryQuery
    expected_memory_ids: list[str] = Field(default_factory=list)
    summary: str = Field(min_length=1)


class TaskMemoryEvaluationChannelResult(StrictModel):
    evaluation_case_id: str = Field(min_length=1)
    channel: TaskMemoryRetrievalChannel
    top_memory_ids: list[str] = Field(default_factory=list)
    hit_memory_ids: list[str] = Field(default_factory=list)
    missed_memory_ids: list[str] = Field(default_factory=list)
    unexpected_memory_ids: list[str] = Field(default_factory=list)
    match_count: int = Field(default=0, ge=0)
    hit_count: int = Field(default=0, ge=0)
    top_hit: bool = False
    decision: MemoryRetrievalEvaluationDecision
    summary: str = Field(min_length=1)


class TaskMemoryEvaluationResult(StrictModel):
    evaluation_id: str = Field(min_length=1)
    evaluated_cases: int = Field(ge=0)
    passed_channels: int = Field(ge=0)
    failed_channels: int = Field(ge=0)
    hit_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    top_hit_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    writeback_volume: int = Field(default=0, ge=0)
    quality_failure_count: int = Field(default=0, ge=0)
    results: list[TaskMemoryEvaluationChannelResult] = Field(default_factory=list)
    summary: str = Field(min_length=1)


class TaskMemoryEvaluationService:
    def __init__(
        self,
        *,
        store: TaskMemoryStore,
        memory_runtime: TaskMemoryRuntime | None = None,
    ) -> None:
        self._store = store
        self._retrieval = TaskMemoryRetrievalService(store=store)
        self._memory_runtime = memory_runtime

    def evaluate_cases(self, cases: list[TaskMemoryEvaluationCase]) -> TaskMemoryEvaluationResult:
        results: list[TaskMemoryEvaluationChannelResult] = []
        for case in cases:
            deterministic = self._retrieval.deterministic_retrieve(case.query)
            vector = self._vector_result(case.query)
            hybrid = self._hybrid_result(case.query)
            no_memory = TaskMemoryRetrievalResult(
                query=case.query,
                channel=TaskMemoryRetrievalChannel.NONE,
                matches=[],
                summary="No-memory baseline returns no retrieved memory.",
            )
            for result in (deterministic, vector, hybrid, no_memory):
                results.append(self._evaluate_channel(case, result))
        passed = sum(1 for result in results if result.decision == MemoryRetrievalEvaluationDecision.PASSED)
        failed = len(results) - passed
        channels_with_expectations = [result for result in results if result.channel != TaskMemoryRetrievalChannel.NONE]
        hit_rate = (
            sum(1 for result in channels_with_expectations if result.hit_count > 0) / len(channels_with_expectations)
            if channels_with_expectations
            else 0.0
        )
        top_hit_rate = (
            sum(1 for result in channels_with_expectations if result.top_hit) / len(channels_with_expectations)
            if channels_with_expectations
            else 0.0
        )
        writeback_results = self._memory_runtime.writeback_results() if self._memory_runtime is not None else []
        writeback_volume = sum(len(result.stored_records) for result in writeback_results)
        quality_failure_count = sum(result.rejected_count for result in writeback_results)
        return TaskMemoryEvaluationResult(
            evaluation_id=build_memory_retrieval_evaluation_id(),
            evaluated_cases=len(cases),
            passed_channels=passed,
            failed_channels=failed,
            hit_rate=hit_rate,
            top_hit_rate=top_hit_rate,
            writeback_volume=writeback_volume,
            quality_failure_count=quality_failure_count,
            results=results,
            summary=(
                f"Evaluated {len(cases)} task memory case(s); passed_channels={passed}, "
                f"failed_channels={failed}, hit_rate={hit_rate:.2f}, top_hit_rate={top_hit_rate:.2f}, "
                f"writeback_volume={writeback_volume}, quality_failures={quality_failure_count}."
            ),
        )

    def _vector_result(self, query: TaskMemoryQuery) -> TaskMemoryRetrievalResult:
        if self._memory_runtime is None:
            return TaskMemoryRetrievalResult(
                query=query,
                channel=TaskMemoryRetrievalChannel.VECTOR,
                matches=[],
                summary="Vector retrieval unavailable because no memory runtime was configured.",
            )
        vector = self._memory_runtime.embed_query(query.semantic_query_text)
        profile_name = self._memory_runtime.embedding_profile_name
        records = self._store.query_records(query)
        self._memory_runtime.ensure_record_embeddings(records)
        return self._retrieval.vector_retrieve(query, query_vector=vector, profile_name=profile_name)

    def _hybrid_result(self, query: TaskMemoryQuery) -> TaskMemoryRetrievalResult:
        if self._memory_runtime is None:
            return self._retrieval.deterministic_retrieve(query).model_copy(
                update={
                    "channel": TaskMemoryRetrievalChannel.HYBRID,
                    "summary": "Hybrid retrieval degraded to deterministic because no memory runtime was configured.",
                }
            )
        vector = self._memory_runtime.embed_query(query.semantic_query_text)
        profile_name = self._memory_runtime.embedding_profile_name
        records = self._store.query_records(query)
        self._memory_runtime.ensure_record_embeddings(records)
        return self._retrieval.hybrid_retrieve(query, query_vector=vector, profile_name=profile_name)

    @staticmethod
    def _evaluate_channel(
        case: TaskMemoryEvaluationCase,
        result: TaskMemoryRetrievalResult,
    ) -> TaskMemoryEvaluationChannelResult:
        top_memory_ids = [match.record.memory_id for match in result.matches]
        hit_memory_ids = [memory_id for memory_id in top_memory_ids if memory_id in case.expected_memory_ids]
        missed_memory_ids = [memory_id for memory_id in case.expected_memory_ids if memory_id not in hit_memory_ids]
        unexpected_memory_ids = [memory_id for memory_id in top_memory_ids if memory_id not in case.expected_memory_ids]
        top_hit = bool(top_memory_ids) and top_memory_ids[0] in case.expected_memory_ids
        decision = (
            MemoryRetrievalEvaluationDecision.PASSED
            if hit_memory_ids
            else MemoryRetrievalEvaluationDecision.FAILED
        )
        return TaskMemoryEvaluationChannelResult(
            evaluation_case_id=case.evaluation_case_id,
            channel=result.channel,
            top_memory_ids=top_memory_ids,
            hit_memory_ids=hit_memory_ids,
            missed_memory_ids=missed_memory_ids,
            unexpected_memory_ids=unexpected_memory_ids,
            match_count=len(top_memory_ids),
            hit_count=len(hit_memory_ids),
            top_hit=top_hit,
            decision=decision,
            summary=(
                f"Task memory channel {result.channel.value} returned "
                f"{top_memory_ids or ['<none>']} with hit_count={len(hit_memory_ids)}."
            ),
        )
