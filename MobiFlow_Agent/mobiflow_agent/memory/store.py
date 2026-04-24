from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from time import time
from typing import Protocol

from mobiflow_agent.memory.models import (
    TaskMemoryEmbeddingEntry,
    TaskMemoryQuery,
    TaskMemoryRecord,
    TaskMemoryRecordStatus,
)

TASK_MEMORY_SCHEMA_VERSION = 2


class TaskMemoryStore(Protocol):
    def put_record(self, record: TaskMemoryRecord) -> TaskMemoryRecord:
        """Create or update a task memory record."""

    def get_record(self, memory_id: str) -> TaskMemoryRecord | None:
        """Load a single task memory record when present."""

    def query_records(self, query: TaskMemoryQuery) -> list[TaskMemoryRecord]:
        """Return deterministically filtered task memory records."""

    def list_records(self, *, statuses: list[TaskMemoryRecordStatus] | None = None) -> list[TaskMemoryRecord]:
        """Return every persisted task memory record."""

    def delete_record(self, memory_id: str) -> None:
        """Delete a persisted task memory record."""

    def update_record_status(
        self,
        memory_id: str,
        status: TaskMemoryRecordStatus,
        *,
        updated_at_ms: int | None = None,
        superseded_by: str | None = None,
        governance_tags: list[str] | None = None,
    ) -> TaskMemoryRecord | None:
        """Transition a record status without deleting it."""

    def touch_record(self, memory_id: str, *, accessed_at_ms: int | None = None) -> TaskMemoryRecord | None:
        """Update access metadata for retrieval observability."""

    def upsert_embedding(self, entry: TaskMemoryEmbeddingEntry) -> TaskMemoryEmbeddingEntry:
        """Create or update the stored embedding entry for a task memory record."""

    def list_embeddings(self, *, profile_name: str | None = None) -> list[TaskMemoryEmbeddingEntry]:
        """Return stored embedding entries."""


class InMemoryTaskMemoryStore:
    def __init__(self) -> None:
        self._records: dict[str, TaskMemoryRecord] = {}
        self._embeddings: dict[tuple[str, str], TaskMemoryEmbeddingEntry] = {}

    def put_record(self, record: TaskMemoryRecord) -> TaskMemoryRecord:
        self._records[record.memory_id] = record.model_copy(deep=True)
        return record

    def get_record(self, memory_id: str) -> TaskMemoryRecord | None:
        record = self._records.get(memory_id)
        return record.model_copy(deep=True) if record is not None else None

    def query_records(self, query: TaskMemoryQuery) -> list[TaskMemoryRecord]:
        return [record.model_copy(deep=True) for record in self._filter_records(query)]

    def list_records(self, *, statuses: list[TaskMemoryRecordStatus] | None = None) -> list[TaskMemoryRecord]:
        records = sorted(self._records.values(), key=lambda item: item.memory_id)
        if statuses is not None:
            allowed = set(statuses)
            records = [record for record in records if record.status in allowed]
        return [record.model_copy(deep=True) for record in records]

    def delete_record(self, memory_id: str) -> None:
        self._records.pop(memory_id, None)
        for key in [key for key in self._embeddings if key[0] == memory_id]:
            self._embeddings.pop(key, None)

    def update_record_status(
        self,
        memory_id: str,
        status: TaskMemoryRecordStatus,
        *,
        updated_at_ms: int | None = None,
        superseded_by: str | None = None,
        governance_tags: list[str] | None = None,
    ) -> TaskMemoryRecord | None:
        record = self._records.get(memory_id)
        if record is None:
            return None
        merged_tags = self._merge_tags(record.governance_tags, governance_tags or [])
        updated = record.model_copy(
            update={
                "status": status,
                "updated_at_ms": updated_at_ms if updated_at_ms is not None else build_memory_timestamp_ms(),
                "superseded_by": superseded_by if superseded_by is not None else record.superseded_by,
                "governance_tags": merged_tags,
            }
        )
        self._records[memory_id] = updated
        return updated.model_copy(deep=True)

    def touch_record(self, memory_id: str, *, accessed_at_ms: int | None = None) -> TaskMemoryRecord | None:
        record = self._records.get(memory_id)
        if record is None:
            return None
        updated = record.model_copy(
            update={
                "last_accessed_at_ms": accessed_at_ms if accessed_at_ms is not None else build_memory_timestamp_ms(),
                "access_count": record.access_count + 1,
            }
        )
        self._records[memory_id] = updated
        return updated.model_copy(deep=True)

    def upsert_embedding(self, entry: TaskMemoryEmbeddingEntry) -> TaskMemoryEmbeddingEntry:
        self._embeddings[(entry.memory_id, entry.profile_name)] = entry.model_copy(deep=True)
        return entry

    def list_embeddings(self, *, profile_name: str | None = None) -> list[TaskMemoryEmbeddingEntry]:
        entries = list(self._embeddings.values())
        if profile_name is not None:
            entries = [entry for entry in entries if entry.profile_name == profile_name]
        return [entry.model_copy(deep=True) for entry in sorted(entries, key=lambda item: (item.profile_name, item.memory_id))]

    def _filter_records(self, query: TaskMemoryQuery) -> list[TaskMemoryRecord]:
        matches: list[TaskMemoryRecord] = []
        required_tags = {tag.casefold() for tag in query.tags}
        goal_text = (query.goal_text or "").casefold()
        now_ms = build_memory_timestamp_ms()
        allowed_statuses = set(query.statuses or [TaskMemoryRecordStatus.ACTIVE])
        for record in self._records.values():
            if record.status not in allowed_statuses:
                continue
            if (
                not query.include_expired
                and record.expires_at_ms is not None
                and record.expires_at_ms <= now_ms
            ):
                continue
            if query.role_scope is not None and record.role_scope != query.role_scope:
                continue
            if query.step_kind is not None and record.step_kind != query.step_kind:
                continue
            if query.kinds and record.kind not in query.kinds:
                continue
            if query.target_kind is not None and record.target_kind != query.target_kind:
                continue
            if query.target_id is not None and record.target_id != query.target_id:
                continue
            if query.verdict_statuses and record.verdict_status not in query.verdict_statuses:
                continue
            if query.blocked_reason is not None and record.blocked_reason != query.blocked_reason:
                continue
            record_tags = {tag.casefold() for tag in record.tags}
            if required_tags and not required_tags.intersection(record_tags):
                continue
            if goal_text and goal_text not in f"{record.goal} {record.summary}".casefold():
                continue
            matches.append(record)
        matches.sort(key=lambda item: (item.updated_at_ms, item.created_at_ms, item.memory_id), reverse=True)
        return matches[: query.top_k * 10]

    @staticmethod
    def _merge_tags(left: list[str], right: list[str]) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()
        for raw_tag in [*left, *right]:
            tag = raw_tag.strip()
            if not tag or tag.casefold() in seen:
                continue
            seen.add(tag.casefold())
            merged.append(tag)
        return merged


class SqliteTaskMemoryStore:
    def __init__(self, path: str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self._path)
        self._connection.row_factory = sqlite3.Row
        self._initialize()

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def __enter__(self) -> "SqliteTaskMemoryStore":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def put_record(self, record: TaskMemoryRecord) -> TaskMemoryRecord:
        payload = json.dumps(record.model_dump(mode="json"), ensure_ascii=False)
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO task_memory_records (
                    memory_id, schema_version, kind, role_scope, target_kind, target_id,
                    verdict_status, blocked_reason, status, expires_at_ms, last_accessed_at_ms,
                    access_count, created_at_ms, updated_at_ms, payload
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(memory_id) DO UPDATE SET
                    kind=excluded.kind,
                    role_scope=excluded.role_scope,
                    target_kind=excluded.target_kind,
                    target_id=excluded.target_id,
                    verdict_status=excluded.verdict_status,
                    blocked_reason=excluded.blocked_reason,
                    status=excluded.status,
                    expires_at_ms=excluded.expires_at_ms,
                    last_accessed_at_ms=excluded.last_accessed_at_ms,
                    access_count=excluded.access_count,
                    created_at_ms=task_memory_records.created_at_ms,
                    updated_at_ms=excluded.updated_at_ms,
                    payload=excluded.payload
                """,
                (
                    record.memory_id,
                    TASK_MEMORY_SCHEMA_VERSION,
                    record.kind.value,
                    record.role_scope,
                    record.target_kind.value if record.target_kind is not None else None,
                    record.target_id,
                    record.verdict_status.value if record.verdict_status is not None else None,
                    record.blocked_reason,
                    record.status.value,
                    record.expires_at_ms,
                    record.last_accessed_at_ms,
                    record.access_count,
                    record.created_at_ms,
                    record.updated_at_ms,
                    payload,
                ),
            )
        return record

    def get_record(self, memory_id: str) -> TaskMemoryRecord | None:
        row = self._connection.execute(
            "SELECT payload FROM task_memory_records WHERE memory_id = ?",
            (memory_id,),
        ).fetchone()
        if row is None:
            return None
        return TaskMemoryRecord.model_validate(json.loads(row["payload"]))

    def query_records(self, query: TaskMemoryQuery) -> list[TaskMemoryRecord]:
        return self._filter_records(query)

    def list_records(self, *, statuses: list[TaskMemoryRecordStatus] | None = None) -> list[TaskMemoryRecord]:
        if statuses is None:
            rows = self._connection.execute(
                "SELECT payload FROM task_memory_records ORDER BY updated_at_ms DESC, memory_id ASC"
            ).fetchall()
        else:
            values = [status.value for status in statuses]
            placeholders = ", ".join("?" for _ in values)
            rows = self._connection.execute(
                f"SELECT payload FROM task_memory_records WHERE status IN ({placeholders}) "
                "ORDER BY updated_at_ms DESC, memory_id ASC",
                values,
            ).fetchall()
        return [TaskMemoryRecord.model_validate(json.loads(row["payload"])) for row in rows]

    def delete_record(self, memory_id: str) -> None:
        with self._connection:
            self._connection.execute("DELETE FROM task_memory_records WHERE memory_id = ?", (memory_id,))
            self._connection.execute("DELETE FROM task_memory_embeddings WHERE memory_id = ?", (memory_id,))

    def update_record_status(
        self,
        memory_id: str,
        status: TaskMemoryRecordStatus,
        *,
        updated_at_ms: int | None = None,
        superseded_by: str | None = None,
        governance_tags: list[str] | None = None,
    ) -> TaskMemoryRecord | None:
        record = self.get_record(memory_id)
        if record is None:
            return None
        merged_tags = InMemoryTaskMemoryStore._merge_tags(record.governance_tags, governance_tags or [])
        updated = record.model_copy(
            update={
                "status": status,
                "updated_at_ms": updated_at_ms if updated_at_ms is not None else build_memory_timestamp_ms(),
                "superseded_by": superseded_by if superseded_by is not None else record.superseded_by,
                "governance_tags": merged_tags,
            }
        )
        return self.put_record(updated)

    def touch_record(self, memory_id: str, *, accessed_at_ms: int | None = None) -> TaskMemoryRecord | None:
        record = self.get_record(memory_id)
        if record is None:
            return None
        updated = record.model_copy(
            update={
                "last_accessed_at_ms": accessed_at_ms if accessed_at_ms is not None else build_memory_timestamp_ms(),
                "access_count": record.access_count + 1,
            }
        )
        return self.put_record(updated)

    def upsert_embedding(self, entry: TaskMemoryEmbeddingEntry) -> TaskMemoryEmbeddingEntry:
        payload = json.dumps(entry.model_dump(mode="json"), ensure_ascii=False)
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO task_memory_embeddings (
                    memory_id, profile_name, updated_at_ms, payload
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT(memory_id, profile_name) DO UPDATE SET
                    updated_at_ms=excluded.updated_at_ms,
                    payload=excluded.payload
                """,
                (entry.memory_id, entry.profile_name, entry.updated_at_ms, payload),
            )
        return entry

    def list_embeddings(self, *, profile_name: str | None = None) -> list[TaskMemoryEmbeddingEntry]:
        if profile_name is None:
            rows = self._connection.execute(
                "SELECT payload FROM task_memory_embeddings ORDER BY profile_name ASC, memory_id ASC"
            ).fetchall()
        else:
            rows = self._connection.execute(
                "SELECT payload FROM task_memory_embeddings WHERE profile_name = ? ORDER BY memory_id ASC",
                (profile_name,),
            ).fetchall()
        return [TaskMemoryEmbeddingEntry.model_validate(json.loads(row["payload"])) for row in rows]

    def _filter_records(self, query: TaskMemoryQuery) -> list[TaskMemoryRecord]:
        records = self.list_records()
        temp = InMemoryTaskMemoryStore()
        for record in records:
            temp.put_record(record)
        return temp._filter_records(query)

    def _initialize(self) -> None:
        with self._connection:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS task_memory_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS task_memory_records (
                    memory_id TEXT PRIMARY KEY,
                    schema_version INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    role_scope TEXT,
                    target_kind TEXT,
                    target_id TEXT,
                    verdict_status TEXT,
                    blocked_reason TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    expires_at_ms INTEGER,
                    last_accessed_at_ms INTEGER,
                    access_count INTEGER NOT NULL DEFAULT 0,
                    created_at_ms INTEGER NOT NULL,
                    updated_at_ms INTEGER NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS task_memory_embeddings (
                    memory_id TEXT NOT NULL,
                    profile_name TEXT NOT NULL,
                    updated_at_ms INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (memory_id, profile_name)
                )
                """
            )
            self._connection.execute(
                """
                INSERT OR REPLACE INTO task_memory_metadata(key, value)
                VALUES ('schema_version', ?)
                """,
                (str(TASK_MEMORY_SCHEMA_VERSION),),
            )
            self._migrate_v2_columns()
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_task_memory_records_kind ON task_memory_records(kind)"
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_task_memory_records_role ON task_memory_records(role_scope)"
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_task_memory_records_target ON task_memory_records(target_kind, target_id)"
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_task_memory_records_updated ON task_memory_records(updated_at_ms)"
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_task_memory_records_status ON task_memory_records(status)"
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_task_memory_records_expiry ON task_memory_records(expires_at_ms)"
            )

    def _migrate_v2_columns(self) -> None:
        columns = {
            row["name"]
            for row in self._connection.execute("PRAGMA table_info(task_memory_records)").fetchall()
        }
        migrations = [
            ("status", "ALTER TABLE task_memory_records ADD COLUMN status TEXT NOT NULL DEFAULT 'active'"),
            ("expires_at_ms", "ALTER TABLE task_memory_records ADD COLUMN expires_at_ms INTEGER"),
            ("last_accessed_at_ms", "ALTER TABLE task_memory_records ADD COLUMN last_accessed_at_ms INTEGER"),
            ("access_count", "ALTER TABLE task_memory_records ADD COLUMN access_count INTEGER NOT NULL DEFAULT 0"),
        ]
        for column, statement in migrations:
            if column not in columns:
                self._connection.execute(statement)


def build_memory_timestamp_ms() -> int:
    return int(time() * 1000)


__all__ = [
    "InMemoryTaskMemoryStore",
    "SqliteTaskMemoryStore",
    "TASK_MEMORY_SCHEMA_VERSION",
    "TaskMemoryStore",
    "build_memory_timestamp_ms",
]
