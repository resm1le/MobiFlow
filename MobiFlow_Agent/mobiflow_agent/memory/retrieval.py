from __future__ import annotations

import math
import re
from typing import Iterable

from mobiflow_agent.memory.models import (
    TaskMemoryEmbeddingEntry,
    TaskMemoryMatch,
    TaskMemoryPolicy,
    TaskMemoryQuery,
    TaskMemoryRecord,
    TaskMemoryRetrievalChannel,
    TaskMemoryRetrievalResult,
)
from mobiflow_agent.memory.store import TaskMemoryStore


class TaskMemoryRetrievalService:
    def __init__(self, *, store: TaskMemoryStore, policy: TaskMemoryPolicy | None = None) -> None:
        self._store = store
        self._policy = policy or TaskMemoryPolicy()

    def deterministic_retrieve(self, query: TaskMemoryQuery) -> TaskMemoryRetrievalResult:
        candidates = self._store.query_records(query)
        matches: list[TaskMemoryMatch] = []
        for record in candidates:
            matched_terms, score = self._deterministic_score(query, record)
            if score < query.min_score:
                continue
            matches.append(
                TaskMemoryMatch(
                    record=record,
                    score=score,
                    channel=TaskMemoryRetrievalChannel.DETERMINISTIC,
                    matched_terms=matched_terms,
                    summary=f"Deterministic memory match score={score:.3f}.",
                )
            )
        matches.sort(key=lambda item: (-item.score, item.record.updated_at_ms, item.record.memory_id))
        limited = matches[: query.top_k]
        return TaskMemoryRetrievalResult(
            query=query,
            channel=TaskMemoryRetrievalChannel.DETERMINISTIC,
            matches=limited,
            summary=f"Retrieved {len(limited)} deterministic task memory match(es).",
        )

    def vector_retrieve(
        self,
        query: TaskMemoryQuery,
        *,
        query_vector: list[float] | None,
        profile_name: str | None,
    ) -> TaskMemoryRetrievalResult:
        if not query.semantic_query_text or query_vector is None or not profile_name:
            return TaskMemoryRetrievalResult(
                query=query,
                channel=TaskMemoryRetrievalChannel.VECTOR,
                matches=[],
                summary="Vector retrieval was skipped because no embedding query was available.",
            )
        candidates = {record.memory_id: record for record in self._store.query_records(query)}
        embeddings = {
            entry.memory_id: entry
            for entry in self._store.list_embeddings(profile_name=profile_name)
            if entry.memory_id in candidates
        }
        matches: list[TaskMemoryMatch] = []
        for memory_id, record in candidates.items():
            entry = embeddings.get(memory_id)
            if entry is None:
                continue
            score = self._cosine_similarity(query_vector, entry.vector)
            if score < query.min_score:
                continue
            matches.append(
                TaskMemoryMatch(
                    record=record,
                    score=score,
                    channel=TaskMemoryRetrievalChannel.VECTOR,
                    matched_terms=[],
                    summary=f"Vector memory match score={score:.3f}.",
                )
            )
        matches.sort(key=lambda item: (-item.score, item.record.updated_at_ms, item.record.memory_id))
        limited = matches[: query.top_k]
        return TaskMemoryRetrievalResult(
            query=query,
            channel=TaskMemoryRetrievalChannel.VECTOR,
            matches=limited,
            summary=f"Retrieved {len(limited)} vector task memory match(es).",
        )

    def hybrid_retrieve(
        self,
        query: TaskMemoryQuery,
        *,
        query_vector: list[float] | None,
        profile_name: str | None,
    ) -> TaskMemoryRetrievalResult:
        deterministic = self.deterministic_retrieve(query)
        vector = self.vector_retrieve(query, query_vector=query_vector, profile_name=profile_name)
        merged: dict[str, TaskMemoryMatch] = {}
        for match in deterministic.matches:
            merged[match.record.memory_id] = match.model_copy(deep=True)
        for match in vector.matches:
            existing = merged.get(match.record.memory_id)
            if existing is None:
                merged[match.record.memory_id] = match.model_copy(deep=True)
                continue
            merged[match.record.memory_id] = existing.model_copy(
                update={
                    "channel": TaskMemoryRetrievalChannel.HYBRID,
                    "score": (
                        existing.score * self._policy.deterministic_weight
                        + match.score * self._policy.vector_weight
                    ),
                    "summary": (
                        f"Hybrid memory match det={existing.score:.3f}, vector={match.score:.3f}."
                    ),
                }
            )
        results = []
        for match in merged.values():
            if match.channel != TaskMemoryRetrievalChannel.HYBRID:
                score = match.score * (
                    self._policy.deterministic_weight
                    if match.channel == TaskMemoryRetrievalChannel.DETERMINISTIC
                    else self._policy.vector_weight
                )
                match = match.model_copy(
                    update={
                        "channel": TaskMemoryRetrievalChannel.HYBRID,
                        "score": score,
                        "summary": f"Hybrid memory match score={score:.3f}.",
                    }
                )
            results.append(match)
        results.sort(key=lambda item: (-item.score, item.record.updated_at_ms, item.record.memory_id))
        limited = results[: query.top_k]
        return TaskMemoryRetrievalResult(
            query=query,
            channel=TaskMemoryRetrievalChannel.HYBRID,
            matches=limited,
            summary=f"Retrieved {len(limited)} hybrid task memory match(es).",
        )

    def ensure_embeddings(
        self,
        records: Iterable[TaskMemoryRecord],
        *,
        profile_name: str,
        embedder,
        render_text,
    ) -> list[TaskMemoryEmbeddingEntry]:
        existing = {
            (entry.memory_id, entry.profile_name): entry
            for entry in self._store.list_embeddings(profile_name=profile_name)
        }
        produced: list[TaskMemoryEmbeddingEntry] = []
        for record in records:
            key = (record.memory_id, profile_name)
            if key in existing:
                produced.append(existing[key])
                continue
            source_text = render_text(record)
            vector = embedder(source_text)
            entry = TaskMemoryEmbeddingEntry(
                memory_id=record.memory_id,
                profile_name=profile_name,
                vector=vector,
                source_text=source_text,
                updated_at_ms=record.updated_at_ms,
            )
            self._store.upsert_embedding(entry)
            produced.append(entry)
        return produced

    @staticmethod
    def _deterministic_score(query: TaskMemoryQuery, record: TaskMemoryRecord) -> tuple[list[str], float]:
        query_terms = set(TaskMemoryRetrievalService._tokenize(" ".join(filter(None, [query.goal_text, query.semantic_query_text]))))
        record_terms = set(TaskMemoryRetrievalService._tokenize(" ".join([record.goal, record.summary, " ".join(record.tags)])))
        matched_terms = sorted(query_terms.intersection(record_terms))
        score = 0.0
        if matched_terms and query_terms:
            score += len(matched_terms) / len(query_terms)
        if query.target_id is not None and query.target_id == record.target_id:
            score += 0.3
        if query.target_kind is not None and query.target_kind == record.target_kind:
            score += 0.1
        if query.blocked_reason is not None and query.blocked_reason == record.blocked_reason:
            score += 0.3
        if query.tags:
            score += len(set(tag.casefold() for tag in query.tags).intersection(tag.casefold() for tag in record.tags)) * 0.1
        return matched_terms, score

    @staticmethod
    def _cosine_similarity(left: list[float], right: list[float]) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        numerator = sum(a * b for a, b in zip(left, right))
        left_norm = math.sqrt(sum(a * a for a in left))
        right_norm = math.sqrt(sum(b * b for b in right))
        if left_norm == 0.0 or right_norm == 0.0:
            return 0.0
        return numerator / (left_norm * right_norm)

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return [token for token in re.findall(r"[a-z0-9_]+", text.casefold()) if len(token) >= 3]


__all__ = ["TaskMemoryRetrievalService"]
