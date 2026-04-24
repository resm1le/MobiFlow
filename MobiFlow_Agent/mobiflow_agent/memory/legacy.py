from __future__ import annotations

from pydantic import Field

from mobiflow_agent.common.contracts import StrictModel
from mobiflow_agent.memory.case import RecoveryMemoryCase, recovery_case_to_task_memory_record
from mobiflow_agent.memory.catalog import MemoryCasePersistenceService
from mobiflow_agent.memory.governance import (
    TaskMemoryGovernanceDecision,
    TaskMemoryGovernanceIssue,
    TaskMemoryGovernanceService,
)
from mobiflow_agent.memory.models import TaskMemoryPolicy, TaskMemoryRecord
from mobiflow_agent.memory.quality import (
    TaskMemoryQualityIssue,
    TaskMemoryQualityService,
)
from mobiflow_agent.memory.store import TaskMemoryStore, build_memory_timestamp_ms


class TaskMemoryLegacyImportResult(StrictModel):
    imported_cases: int = Field(ge=0)
    created_count: int = Field(ge=0)
    updated_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    quarantined_count: int = Field(default=0, ge=0)
    superseded_count: int = Field(default=0, ge=0)
    stored_records: list[TaskMemoryRecord] = Field(default_factory=list)
    rejected_records: list[TaskMemoryRecord] = Field(default_factory=list)
    quality_issues: list[TaskMemoryQualityIssue] = Field(default_factory=list)
    governance_issues: list[TaskMemoryGovernanceIssue] = Field(default_factory=list)
    summary: str = Field(min_length=1)


class TaskMemoryLegacyImportService:
    def __init__(
        self,
        *,
        store: TaskMemoryStore,
        quality_service: TaskMemoryQualityService | None = None,
        governance_service: TaskMemoryGovernanceService | None = None,
        persistence_service: MemoryCasePersistenceService | None = None,
        policy: TaskMemoryPolicy | None = None,
    ) -> None:
        self._store = store
        self._quality_service = quality_service or TaskMemoryQualityService()
        self._governance_service = governance_service or TaskMemoryGovernanceService()
        self._persistence_service = persistence_service or MemoryCasePersistenceService()
        self._policy = policy or TaskMemoryPolicy()

    def import_cases(self, cases: list[RecoveryMemoryCase]) -> TaskMemoryLegacyImportResult:
        stored_records: list[TaskMemoryRecord] = []
        rejected_records: list[TaskMemoryRecord] = []
        quality_issues: list[TaskMemoryQualityIssue] = []
        governance_issues: list[TaskMemoryGovernanceIssue] = []
        created_count = 0
        updated_count = 0
        quarantined_count = 0
        superseded_count = 0
        now_ms = build_memory_timestamp_ms()

        for legacy_case in cases:
            record = recovery_case_to_task_memory_record(legacy_case).model_copy(
                update={"created_at_ms": now_ms, "updated_at_ms": now_ms}
            )
            assessment = self._quality_service.assess_record(record, policy=self._policy)
            quality_issues.extend(assessment.issues)
            existing = self._store.get_record(record.memory_id)
            governance = self._governance_service.govern_record(
                record,
                quality_assessment=assessment,
                existing_record=existing,
                now_ms=now_ms,
            )
            governance_issues.extend(governance.issues)
            if governance.decision == TaskMemoryGovernanceDecision.REJECTED or governance.record is None:
                rejected_records.append(record)
                continue

            if existing is None:
                created_count += 1
            else:
                updated_count += 1
            if governance.decision == TaskMemoryGovernanceDecision.QUARANTINED:
                quarantined_count += 1
            record_to_store = governance.record
            self._store.put_record(record_to_store)
            stored_records.append(record_to_store)
            if record_to_store.proposal_fingerprint is not None:
                governance_report = self._governance_service.supersede_excess_versions(
                    self._store,
                    proposal_fingerprint=record_to_store.proposal_fingerprint,
                    keep_memory_id=record_to_store.memory_id,
                    now_ms=now_ms,
                )
                superseded_count += governance_report.superseded_count
                governance_issues.extend(governance_report.issues)

        return TaskMemoryLegacyImportResult(
            imported_cases=len(cases),
            created_count=created_count,
            updated_count=updated_count,
            rejected_count=len(rejected_records),
            quarantined_count=quarantined_count,
            superseded_count=superseded_count,
            stored_records=stored_records,
            rejected_records=rejected_records,
            quality_issues=quality_issues,
            governance_issues=governance_issues,
            summary=(
                f"Imported {len(cases)} legacy recovery memory case(s): "
                f"created={created_count}, updated={updated_count}, rejected={len(rejected_records)}, "
                f"quarantined={quarantined_count}, superseded={superseded_count}."
            ),
        )

    def import_catalog(self, catalog_dir: str) -> TaskMemoryLegacyImportResult:
        catalog = self._persistence_service.list_catalog(catalog_dir)
        cases = [self._persistence_service.load_case(entry.path) for entry in catalog.entries]
        return self.import_cases(cases)


__all__ = ["TaskMemoryLegacyImportResult", "TaskMemoryLegacyImportService"]
