from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from mobiflow_agent.runtime.harness.errors import TaskHarnessSerializationError, TaskHarnessStoreError
from mobiflow_agent.runtime.harness.models import TASK_HARNESS_SCHEMA_VERSION, TaskHarnessJob, TaskHarnessStatus


class TaskHarnessStore(Protocol):
    def save_job(self, job: TaskHarnessJob) -> TaskHarnessJob:
        """Persist a harness job."""

    def get_job(self, job_id: str) -> TaskHarnessJob:
        """Load one harness job by id."""

    def list_due_jobs(self, *, now_ms: int, limit: int = 20) -> list[TaskHarnessJob]:
        """Return due scheduled jobs ordered by wakeup time."""


class InMemoryTaskHarnessStore:
    def __init__(self) -> None:
        self._jobs: dict[str, TaskHarnessJob] = {}

    def save_job(self, job: TaskHarnessJob) -> TaskHarnessJob:
        stored = job.model_copy(deep=True)
        self._jobs[job.job_id] = stored
        return stored.model_copy(deep=True)

    def get_job(self, job_id: str) -> TaskHarnessJob:
        try:
            return self._jobs[job_id].model_copy(deep=True)
        except KeyError as exc:
            raise TaskHarnessStoreError(f"Task harness job was not found: {job_id}") from exc

    def list_due_jobs(self, *, now_ms: int, limit: int = 20) -> list[TaskHarnessJob]:
        due_jobs = [
            job.model_copy(deep=True)
            for job in self._jobs.values()
            if job.status == TaskHarnessStatus.SCHEDULED
            and job.next_wakeup_at is not None
            and job.next_wakeup_at <= now_ms
        ]
        due_jobs.sort(key=lambda item: (item.next_wakeup_at or 0, item.job_id))
        return due_jobs[:limit]


class SqliteTaskHarnessStore:
    def __init__(self, sqlite_path: str) -> None:
        path = Path(sqlite_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path, check_same_thread=False)
        self._closed = False
        self._initialize_schema()

    def __enter__(self) -> "SqliteTaskHarnessStore":
        self._ensure_open()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def save_job(self, job: TaskHarnessJob) -> TaskHarnessJob:
        self._ensure_open()
        try:
            payload = job.model_dump_json()
            with self._connection:
                self._connection.execute(
                    """
                    INSERT INTO task_harness_jobs (
                        job_id,
                        schema_version,
                        status,
                        next_wakeup_at,
                        created_at_ms,
                        updated_at_ms,
                        failure_count,
                        payload
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(job_id) DO UPDATE SET
                        schema_version = excluded.schema_version,
                        status = excluded.status,
                        next_wakeup_at = excluded.next_wakeup_at,
                        updated_at_ms = excluded.updated_at_ms,
                        failure_count = excluded.failure_count,
                        payload = excluded.payload
                    """,
                    (
                        job.job_id,
                        job.schema_version,
                        job.status.value,
                        job.next_wakeup_at,
                        job.created_at_ms,
                        job.updated_at_ms,
                        job.failure_count,
                        payload,
                    ),
                )
            return TaskHarnessJob.model_validate_json(payload)
        except sqlite3.Error as exc:
            raise TaskHarnessStoreError(f"Failed to persist task harness job {job.job_id}.") from exc
        except ValidationError as exc:
            raise TaskHarnessSerializationError(
                f"Failed to re-read persisted task harness job payload: {job.job_id}."
            ) from exc

    def get_job(self, job_id: str) -> TaskHarnessJob:
        self._ensure_open()
        try:
            cursor = self._connection.execute(
                "SELECT payload FROM task_harness_jobs WHERE job_id = ?",
                (job_id,),
            )
            row = cursor.fetchone()
        except sqlite3.Error as exc:
            raise TaskHarnessStoreError(f"Failed to load task harness job {job_id}.") from exc
        if row is None:
            raise TaskHarnessStoreError(f"Task harness job was not found: {job_id}")
        return self._decode_job_payload(row[0], job_id=job_id)

    def list_due_jobs(self, *, now_ms: int, limit: int = 20) -> list[TaskHarnessJob]:
        self._ensure_open()
        try:
            cursor = self._connection.execute(
                """
                SELECT job_id, payload
                FROM task_harness_jobs
                WHERE status = ? AND next_wakeup_at IS NOT NULL AND next_wakeup_at <= ?
                ORDER BY next_wakeup_at ASC, job_id ASC
                LIMIT ?
                """,
                (TaskHarnessStatus.SCHEDULED.value, now_ms, limit),
            )
            rows = cursor.fetchall()
        except sqlite3.Error as exc:
            raise TaskHarnessStoreError("Failed to list due task harness jobs.") from exc
        return [self._decode_job_payload(payload, job_id=job_id) for job_id, payload in rows]

    def close(self) -> None:
        if self._closed:
            return
        self._connection.close()
        self._closed = True

    def _initialize_schema(self) -> None:
        try:
            with self._connection:
                self._connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS task_harness_metadata (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                    """
                )
                self._connection.execute(
                    """
                    INSERT INTO task_harness_metadata (key, value)
                    VALUES ('schema_version', ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (str(TASK_HARNESS_SCHEMA_VERSION),),
                )
                self._connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS task_harness_jobs (
                        job_id TEXT PRIMARY KEY,
                        schema_version INTEGER NOT NULL,
                        status TEXT NOT NULL,
                        next_wakeup_at INTEGER,
                        created_at_ms INTEGER NOT NULL,
                        updated_at_ms INTEGER NOT NULL,
                        failure_count INTEGER NOT NULL,
                        payload TEXT NOT NULL
                    )
                    """
                )
                self._connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_task_harness_jobs_due
                    ON task_harness_jobs(status, next_wakeup_at, job_id)
                    """
                )
                self._connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_task_harness_jobs_updated
                    ON task_harness_jobs(updated_at_ms)
                    """
                )
        except sqlite3.Error as exc:
            raise TaskHarnessStoreError("Failed to initialize task harness SQLite schema.") from exc

    def _ensure_open(self) -> None:
        if self._closed:
            raise TaskHarnessStoreError("Task harness SQLite store is closed.")

    @staticmethod
    def _decode_job_payload(payload: str, *, job_id: str) -> TaskHarnessJob:
        try:
            return TaskHarnessJob.model_validate_json(payload)
        except (ValidationError, ValueError) as exc:
            raise TaskHarnessSerializationError(
                f"Failed to decode persisted task harness job payload: {job_id}."
            ) from exc


__all__ = [
    "InMemoryTaskHarnessStore",
    "SqliteTaskHarnessStore",
    "TaskHarnessStore",
]
