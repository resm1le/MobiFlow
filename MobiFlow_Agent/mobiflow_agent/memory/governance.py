from __future__ import annotations

from enum import Enum

from pydantic import Field

from mobiflow_agent.common.contracts import StrictModel
from mobiflow_agent.memory.models import TaskMemoryRecord, TaskMemoryRecordStatus
from mobiflow_agent.memory.quality import (
    TaskMemoryQualityAssessment,
    TaskMemoryQualityDecision,
)
from mobiflow_agent.memory.store import TaskMemoryStore, build_memory_timestamp_ms


class TaskMemoryGovernanceDecision(str, Enum):
    ACTIVE = "active"
    UPDATED = "updated"
    QUARANTINED = "quarantined"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


class TaskMemoryGovernancePolicy(StrictModel):
    default_ttl_ms: int | None = Field(default=None, ge=1)
    max_versions_per_fingerprint: int = Field(default=3, ge=1)
    quarantine_failed_quality: bool = True
    quarantine_warning_quality: bool = False
    allow_low_confidence_active: bool = True
    governance_tags: list[str] = Field(default_factory=list)


class TaskMemoryGovernanceIssue(StrictModel):
    code: str = Field(min_length=1)
    memory_id: str = Field(min_length=1)
    summary: str = Field(min_length=1)


class TaskMemoryGovernanceRecordResult(StrictModel):
    record: TaskMemoryRecord | None = None
    decision: TaskMemoryGovernanceDecision
    issues: list[TaskMemoryGovernanceIssue] = Field(default_factory=list)
    summary: str = Field(min_length=1)


class TaskMemoryGovernanceReport(StrictModel):
    evaluated_records: int = Field(ge=0)
    active_count: int = Field(default=0, ge=0)
    updated_count: int = Field(default=0, ge=0)
    quarantined_count: int = Field(default=0, ge=0)
    expired_count: int = Field(default=0, ge=0)
    superseded_count: int = Field(default=0, ge=0)
    rejected_count: int = Field(default=0, ge=0)
    results: list[TaskMemoryGovernanceRecordResult] = Field(default_factory=list)
    issues: list[TaskMemoryGovernanceIssue] = Field(default_factory=list)
    summary: str = Field(min_length=1)


class TaskMemoryGovernanceService:
    def __init__(self, *, policy: TaskMemoryGovernancePolicy | None = None) -> None:
        self._policy = policy or TaskMemoryGovernancePolicy()

    @property
    def policy(self) -> TaskMemoryGovernancePolicy:
        return self._policy

    def govern_record(
        self,
        record: TaskMemoryRecord,
        *,
        quality_assessment: TaskMemoryQualityAssessment,
        existing_record: TaskMemoryRecord | None = None,
        now_ms: int | None = None,
    ) -> TaskMemoryGovernanceRecordResult:
        resolved_now_ms = now_ms if now_ms is not None else build_memory_timestamp_ms()
        issues: list[TaskMemoryGovernanceIssue] = []
        if quality_assessment.decision == TaskMemoryQualityDecision.FAILED:
            if not self._policy.quarantine_failed_quality:
                return TaskMemoryGovernanceRecordResult(
                    record=None,
                    decision=TaskMemoryGovernanceDecision.REJECTED,
                    issues=[
                        self._issue(
                            record,
                            "quality_failed_rejected",
                            "Record failed quality assessment and quarantine is disabled.",
                        )
                    ],
                    summary=f"Task memory record {record.memory_id} was rejected by governance.",
                )
            issues.append(
                self._issue(
                    record,
                    "quality_failed_quarantined",
                    "Record failed quality assessment and was quarantined.",
                )
            )
            return TaskMemoryGovernanceRecordResult(
                record=self._governed_record(
                    record,
                    status=TaskMemoryRecordStatus.QUARANTINED,
                    quality_decision=quality_assessment.decision.value,
                    now_ms=resolved_now_ms,
                    existing_record=existing_record,
                    tags=["quality_failed", *self._policy.governance_tags],
                ),
                decision=TaskMemoryGovernanceDecision.QUARANTINED,
                issues=issues,
                summary=f"Task memory record {record.memory_id} was quarantined by governance.",
            )

        if (
            quality_assessment.decision == TaskMemoryQualityDecision.WARNING
            and self._policy.quarantine_warning_quality
        ):
            issues.append(
                self._issue(
                    record,
                    "quality_warning_quarantined",
                    "Record had quality warnings and was quarantined by policy.",
                )
            )
            return TaskMemoryGovernanceRecordResult(
                record=self._governed_record(
                    record,
                    status=TaskMemoryRecordStatus.QUARANTINED,
                    quality_decision=quality_assessment.decision.value,
                    now_ms=resolved_now_ms,
                    existing_record=existing_record,
                    tags=["quality_warning", *self._policy.governance_tags],
                ),
                decision=TaskMemoryGovernanceDecision.QUARANTINED,
                issues=issues,
                summary=f"Task memory record {record.memory_id} was quarantined by warning policy.",
            )

        decision = (
            TaskMemoryGovernanceDecision.UPDATED
            if existing_record is not None
            else TaskMemoryGovernanceDecision.ACTIVE
        )
        return TaskMemoryGovernanceRecordResult(
            record=self._governed_record(
                record,
                status=TaskMemoryRecordStatus.ACTIVE,
                quality_decision=quality_assessment.decision.value,
                now_ms=resolved_now_ms,
                existing_record=existing_record,
                tags=self._policy.governance_tags,
            ),
            decision=decision,
            summary=f"Task memory record {record.memory_id} is eligible for active retrieval.",
        )

    def expire_due_records(
        self,
        store: TaskMemoryStore,
        *,
        now_ms: int | None = None,
    ) -> TaskMemoryGovernanceReport:
        resolved_now_ms = now_ms if now_ms is not None else build_memory_timestamp_ms()
        results: list[TaskMemoryGovernanceRecordResult] = []
        for record in store.list_records(statuses=[TaskMemoryRecordStatus.ACTIVE]):
            if record.expires_at_ms is None or record.expires_at_ms > resolved_now_ms:
                continue
            expired = store.update_record_status(
                record.memory_id,
                TaskMemoryRecordStatus.EXPIRED,
                updated_at_ms=resolved_now_ms,
                governance_tags=["ttl_expired"],
            )
            results.append(
                TaskMemoryGovernanceRecordResult(
                    record=expired,
                    decision=TaskMemoryGovernanceDecision.EXPIRED,
                    issues=[
                        self._issue(record, "ttl_expired", "Record TTL expired and was removed from retrieval.")
                    ],
                    summary=f"Task memory record {record.memory_id} expired.",
                )
            )
        return self._report(results)

    def supersede_excess_versions(
        self,
        store: TaskMemoryStore,
        *,
        proposal_fingerprint: str,
        keep_memory_id: str,
        now_ms: int | None = None,
    ) -> TaskMemoryGovernanceReport:
        resolved_now_ms = now_ms if now_ms is not None else build_memory_timestamp_ms()
        versions = [
            record
            for record in store.list_records(statuses=[TaskMemoryRecordStatus.ACTIVE])
            if record.proposal_fingerprint == proposal_fingerprint
        ]
        versions.sort(key=lambda item: (item.version, item.updated_at_ms, item.memory_id), reverse=True)
        excess = [record for record in versions[self._policy.max_versions_per_fingerprint :] if record.memory_id != keep_memory_id]
        results: list[TaskMemoryGovernanceRecordResult] = []
        for record in excess:
            superseded = store.update_record_status(
                record.memory_id,
                TaskMemoryRecordStatus.SUPERSEDED,
                updated_at_ms=resolved_now_ms,
                superseded_by=keep_memory_id,
                governance_tags=["version_limit"],
            )
            results.append(
                TaskMemoryGovernanceRecordResult(
                    record=superseded,
                    decision=TaskMemoryGovernanceDecision.SUPERSEDED,
                    issues=[
                        self._issue(
                            record,
                            "version_limit_superseded",
                            "Record exceeded max versions per fingerprint and was superseded.",
                        )
                    ],
                    summary=f"Task memory record {record.memory_id} was superseded by {keep_memory_id}.",
                )
            )
        return self._report(results)

    def _governed_record(
        self,
        record: TaskMemoryRecord,
        *,
        status: TaskMemoryRecordStatus,
        quality_decision: str,
        now_ms: int,
        existing_record: TaskMemoryRecord | None,
        tags: list[str],
    ) -> TaskMemoryRecord:
        version = existing_record.version + 1 if existing_record is not None else max(record.version, 1)
        expires_at_ms = record.expires_at_ms
        if status == TaskMemoryRecordStatus.ACTIVE and expires_at_ms is None and self._policy.default_ttl_ms is not None:
            expires_at_ms = now_ms + self._policy.default_ttl_ms
        return record.model_copy(
            update={
                "status": status,
                "version": version,
                "expires_at_ms": expires_at_ms,
                "quality_decision": quality_decision,
                "governance_tags": self._merge_tags(record.governance_tags, tags),
                "updated_at_ms": now_ms,
                "created_at_ms": existing_record.created_at_ms if existing_record is not None else record.created_at_ms,
                "last_accessed_at_ms": existing_record.last_accessed_at_ms if existing_record is not None else record.last_accessed_at_ms,
                "access_count": existing_record.access_count if existing_record is not None else record.access_count,
            }
        )

    @classmethod
    def _report(cls, results: list[TaskMemoryGovernanceRecordResult]) -> TaskMemoryGovernanceReport:
        issues = [issue for result in results for issue in result.issues]
        return TaskMemoryGovernanceReport(
            evaluated_records=len(results),
            active_count=sum(1 for result in results if result.decision == TaskMemoryGovernanceDecision.ACTIVE),
            updated_count=sum(1 for result in results if result.decision == TaskMemoryGovernanceDecision.UPDATED),
            quarantined_count=sum(1 for result in results if result.decision == TaskMemoryGovernanceDecision.QUARANTINED),
            expired_count=sum(1 for result in results if result.decision == TaskMemoryGovernanceDecision.EXPIRED),
            superseded_count=sum(1 for result in results if result.decision == TaskMemoryGovernanceDecision.SUPERSEDED),
            rejected_count=sum(1 for result in results if result.decision == TaskMemoryGovernanceDecision.REJECTED),
            results=results,
            issues=issues,
            summary=f"Task memory governance evaluated {len(results)} record(s).",
        )

    @staticmethod
    def _issue(record: TaskMemoryRecord, code: str, summary: str) -> TaskMemoryGovernanceIssue:
        return TaskMemoryGovernanceIssue(code=code, memory_id=record.memory_id, summary=summary)

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


__all__ = [
    "TaskMemoryGovernanceDecision",
    "TaskMemoryGovernanceIssue",
    "TaskMemoryGovernancePolicy",
    "TaskMemoryGovernanceRecordResult",
    "TaskMemoryGovernanceReport",
    "TaskMemoryGovernanceService",
]
