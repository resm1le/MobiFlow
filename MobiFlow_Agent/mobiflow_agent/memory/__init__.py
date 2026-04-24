"""Task-first memory subsystem for retrieval, writeback, quality, and evaluation."""

from importlib import import_module

from mobiflow_agent.memory.models import (
    TaskMemoryContext,
    TaskMemoryMatch,
    TaskMemoryPolicy,
    TaskMemoryQuery,
    TaskMemoryRecord,
    TaskMemoryRecordKind,
    TaskMemoryRecordStatus,
    TaskMemoryRetrievalChannel,
    TaskMemoryRetrievalResult,
    TaskMemoryWritebackRequest,
    TaskMemoryWritebackResult,
)
from mobiflow_agent.memory.governance import (
    TaskMemoryGovernanceDecision,
    TaskMemoryGovernanceIssue,
    TaskMemoryGovernancePolicy,
    TaskMemoryGovernanceRecordResult,
    TaskMemoryGovernanceReport,
    TaskMemoryGovernanceService,
)
from mobiflow_agent.memory.quality import (
    TaskMemoryQualityAssessment,
    TaskMemoryQualityDecision,
    TaskMemoryQualityIssue,
    TaskMemoryQualityPolicy,
    TaskMemoryQualityReport,
    TaskMemoryQualityService,
)
from mobiflow_agent.memory.retrieval import TaskMemoryRetrievalService
from mobiflow_agent.memory.runtime import TaskMemoryRuntime
from mobiflow_agent.memory.store import InMemoryTaskMemoryStore, SqliteTaskMemoryStore, TaskMemoryStore

__all__ = [
    "InMemoryTaskMemoryStore",
    "SqliteTaskMemoryStore",
    "TaskMemoryContext",
    "TaskMemoryGovernanceDecision",
    "TaskMemoryGovernanceIssue",
    "TaskMemoryGovernancePolicy",
    "TaskMemoryGovernanceRecordResult",
    "TaskMemoryGovernanceReport",
    "TaskMemoryGovernanceService",
    "TaskMemoryLegacyImportResult",
    "TaskMemoryLegacyImportService",
    "TaskMemoryMatch",
    "TaskMemoryPolicy",
    "TaskMemoryQualityAssessment",
    "TaskMemoryQualityDecision",
    "TaskMemoryQualityIssue",
    "TaskMemoryQualityPolicy",
    "TaskMemoryQualityReport",
    "TaskMemoryQualityService",
    "TaskMemoryQuery",
    "TaskMemoryRecord",
    "TaskMemoryRecordKind",
    "TaskMemoryRecordStatus",
    "TaskMemoryRetrievalChannel",
    "TaskMemoryRetrievalResult",
    "TaskMemoryRetrievalService",
    "TaskMemoryRuntime",
    "TaskMemoryStore",
    "TaskMemoryWritebackRequest",
    "TaskMemoryWritebackResult",
]


def __getattr__(name: str):
    if name in {"TaskMemoryLegacyImportResult", "TaskMemoryLegacyImportService"}:
        legacy = import_module("mobiflow_agent.memory.legacy")
        return getattr(legacy, name)
    raise AttributeError(f"module 'mobiflow_agent.memory' has no attribute {name!r}")
