from __future__ import annotations

"""Benchmark comparison history assets and service."""

from enum import Enum

from pydantic import Field

from mobiflow_agent.common.contracts import StrictModel
from mobiflow_agent.evaluation.benchmark.comparison import RecoveryBenchmarkComparisonKind
from mobiflow_agent.evaluation.benchmark.quality_gate import (
    RecoveryBenchmarkQualityGateDecision,
    RecoveryBenchmarkQualityGatePolicy,
    RecoveryBenchmarkQualityGateViolation,
)
from mobiflow_agent.evaluation.benchmark.comparison import RecoveryBenchmarkComparisonStatus

class RecoveryBenchmarkComparisonHistorySchemaVersion(str, Enum):
    V1 = "v1"

class RecoveryBenchmarkComparisonHistoryEntry(StrictModel):
    comparison_id: str = Field(min_length=1)
    comparison_kind: RecoveryBenchmarkComparisonKind
    baseline_id: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    status: RecoveryBenchmarkComparisonStatus
    gate_decision: RecoveryBenchmarkQualityGateDecision
    violation_count: int = Field(ge=0)
    path: str = Field(min_length=1)
    summary: str = Field(min_length=1)

class RecoveryBenchmarkComparisonHistory(StrictModel):
    schema_version: RecoveryBenchmarkComparisonHistorySchemaVersion = (
        RecoveryBenchmarkComparisonHistorySchemaVersion.V1
    )
    history_id: str = Field(min_length=1)
    source_catalog_dir: str = Field(min_length=1)
    policy: RecoveryBenchmarkQualityGatePolicy
    overall_decision: RecoveryBenchmarkQualityGateDecision
    evaluated_comparisons: int = Field(ge=0)
    passed_comparisons: int = Field(ge=0)
    warning_comparisons: int = Field(ge=0)
    failed_comparisons: int = Field(ge=0)
    entries: list[RecoveryBenchmarkComparisonHistoryEntry] = Field(default_factory=list)
    violations: list[RecoveryBenchmarkQualityGateViolation] = Field(default_factory=list)
    summary: str = Field(min_length=1)

class RecoveryBenchmarkComparisonHistoryDocument(StrictModel):
    schema_version: RecoveryBenchmarkComparisonHistorySchemaVersion = (
        RecoveryBenchmarkComparisonHistorySchemaVersion.V1
    )
    history: RecoveryBenchmarkComparisonHistory

class RecoveryBenchmarkComparisonHistoryCatalogEntry(StrictModel):
    history_id: str = Field(min_length=1)
    source_catalog_dir: str = Field(min_length=1)
    overall_decision: RecoveryBenchmarkQualityGateDecision
    evaluated_comparisons: int = Field(ge=0)
    passed_comparisons: int = Field(ge=0)
    warning_comparisons: int = Field(ge=0)
    failed_comparisons: int = Field(ge=0)
    path: str = Field(min_length=1)
    summary: str = Field(min_length=1)

class RecoveryBenchmarkComparisonHistoryCatalog(StrictModel):
    schema_version: RecoveryBenchmarkComparisonHistorySchemaVersion = (
        RecoveryBenchmarkComparisonHistorySchemaVersion.V1
    )
    catalog_dir: str = Field(min_length=1)
    entries: list[RecoveryBenchmarkComparisonHistoryCatalogEntry] = Field(default_factory=list)
    summary: str = Field(min_length=1)

import json
from hashlib import sha256
from pathlib import Path
from urllib.parse import quote

from pydantic import ValidationError

from mobiflow_agent.evaluation.benchmark.comparison import (
    RecoveryBenchmarkComparisonCatalogEntry,
    RecoveryBenchmarkComparisonKind,
)
from mobiflow_agent.evaluation.benchmark.comparison import (
    RecoveryBenchmarkComparisonPersistenceService,
)
from mobiflow_agent.evaluation.benchmark.quality_gate import (
    RecoveryBenchmarkQualityGateDecision,
    RecoveryBenchmarkQualityGatePolicy,
    RecoveryBenchmarkQualityGateResult,
    RecoveryBenchmarkQualityGateViolation,
)
from mobiflow_agent.evaluation.benchmark.quality_gate import (
    RecoveryBenchmarkQualityGateService,
)

class RecoveryBenchmarkComparisonHistoryService:
    def __init__(
        self,
        *,
        comparison_persistence_service: RecoveryBenchmarkComparisonPersistenceService | None = None,
        quality_gate_service: RecoveryBenchmarkQualityGateService | None = None,
    ) -> None:
        self._comparison_persistence_service = (
            comparison_persistence_service or RecoveryBenchmarkComparisonPersistenceService()
        )
        self._quality_gate_service = quality_gate_service or RecoveryBenchmarkQualityGateService(
            self._comparison_persistence_service
        )

    def build_history(
        self,
        comparison_catalog_dir: str,
        *,
        policy: RecoveryBenchmarkQualityGatePolicy | None = None,
        history_id: str | None = None,
    ) -> RecoveryBenchmarkComparisonHistory:
        resolved_policy = policy or RecoveryBenchmarkQualityGatePolicy()
        catalog = self._comparison_persistence_service.list_catalog(comparison_catalog_dir)
        resolved_history_id = history_id or self._history_id(
            source_catalog_dir=catalog.catalog_dir,
            policy=resolved_policy,
        )

        if not catalog.entries:
            gate_result = self._quality_gate_service.evaluate_comparison_catalog(
                comparison_catalog_dir,
                policy=resolved_policy,
            )
            return self._build_history(
                history_id=resolved_history_id,
                source_catalog_dir=catalog.catalog_dir,
                policy=resolved_policy,
                gate_results=[],
                entries=[],
                violations=gate_result.violations,
                summary=(
                    "Benchmark comparison history failed: "
                    f"{catalog.catalog_dir} has no comparison evidence."
                ),
            )

        gate_results: list[RecoveryBenchmarkQualityGateResult] = []
        history_entries: list[RecoveryBenchmarkComparisonHistoryEntry] = []
        for entry in catalog.entries:
            gate_result = self._evaluate_catalog_entry(entry, policy=resolved_policy)
            gate_results.append(gate_result)
            history_entries.append(
                RecoveryBenchmarkComparisonHistoryEntry(
                    comparison_id=entry.comparison_id,
                    comparison_kind=entry.comparison_kind,
                    baseline_id=entry.baseline_id,
                    candidate_id=entry.candidate_id,
                    status=entry.status,
                    gate_decision=gate_result.decision,
                    violation_count=len(gate_result.violations),
                    path=entry.path,
                    summary=entry.summary,
                )
            )

        decision = self._aggregate_decision([item.decision for item in gate_results])
        violations = [
            violation
            for gate_result in gate_results
            for violation in gate_result.violations
        ]
        return RecoveryBenchmarkComparisonHistory(
            history_id=resolved_history_id,
            source_catalog_dir=catalog.catalog_dir,
            policy=resolved_policy,
            overall_decision=decision,
            evaluated_comparisons=len(gate_results),
            passed_comparisons=sum(
                1
                for item in gate_results
                if item.decision == RecoveryBenchmarkQualityGateDecision.PASSED
            ),
            warning_comparisons=sum(
                1
                for item in gate_results
                if item.decision == RecoveryBenchmarkQualityGateDecision.WARNING
            ),
            failed_comparisons=sum(
                1
                for item in gate_results
                if item.decision == RecoveryBenchmarkQualityGateDecision.FAILED
            ),
            entries=history_entries,
            violations=violations,
            summary=(
                f"Benchmark comparison history {decision.value}: "
                f"{len(gate_results)} comparisons evaluated."
            ),
        )

    def save_history(
        self,
        *,
        history: RecoveryBenchmarkComparisonHistory,
        output_path: str,
    ) -> RecoveryBenchmarkComparisonHistoryCatalogEntry:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        document = RecoveryBenchmarkComparisonHistoryDocument(history=history)
        payload = document.model_dump(mode="json")
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return self._build_catalog_entry(history=history, path=path)

    def load_history(self, path: str) -> RecoveryBenchmarkComparisonHistory:
        document = self._load_document(Path(path))
        return document.history

    def save_to_catalog(
        self,
        *,
        history: RecoveryBenchmarkComparisonHistory,
        catalog_dir: str,
    ) -> RecoveryBenchmarkComparisonHistoryCatalogEntry:
        path = self._catalog_path(Path(catalog_dir), history.history_id)
        return self.save_history(history=history, output_path=str(path))

    def list_catalog(self, catalog_dir: str) -> RecoveryBenchmarkComparisonHistoryCatalog:
        directory = Path(catalog_dir)
        if not directory.exists():
            raise FileNotFoundError(f"Comparison history catalog directory does not exist: {directory}")

        entries = [
            self._build_catalog_entry(history=document.history, path=path)
            for path, document in self._iter_catalog_documents(directory)
        ]
        entries.sort(key=lambda item: item.history_id)
        return RecoveryBenchmarkComparisonHistoryCatalog(
            catalog_dir=str(directory),
            entries=entries,
            summary=(
                f"Benchmark comparison history catalog {directory} contains "
                f"{len(entries)} histories."
            ),
        )

    def _evaluate_catalog_entry(
        self,
        entry: RecoveryBenchmarkComparisonCatalogEntry,
        *,
        policy: RecoveryBenchmarkQualityGatePolicy,
    ) -> RecoveryBenchmarkQualityGateResult:
        if entry.comparison_kind == RecoveryBenchmarkComparisonKind.DATASET:
            comparison = self._comparison_persistence_service.load_dataset_comparison(entry.path)
            return self._quality_gate_service.evaluate_dataset_comparison(
                comparison,
                policy=policy,
            )
        comparison = self._comparison_persistence_service.load_catalog_comparison(entry.path)
        return self._quality_gate_service.evaluate_catalog_comparison(
            comparison,
            policy=policy,
        )

    def _iter_catalog_documents(
        self,
        directory: Path,
    ) -> list[tuple[Path, RecoveryBenchmarkComparisonHistoryDocument]]:
        documents: list[tuple[Path, RecoveryBenchmarkComparisonHistoryDocument]] = []
        for path in sorted(directory.glob("*.json"), key=lambda item: item.name):
            documents.append((path, self._load_document(path)))
        return documents

    @staticmethod
    def _load_document(path: Path) -> RecoveryBenchmarkComparisonHistoryDocument:
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid benchmark comparison history JSON document: {path}") from exc
        try:
            return RecoveryBenchmarkComparisonHistoryDocument.model_validate(payload)
        except ValidationError as exc:
            raise ValueError(
                f"Invalid benchmark comparison history document schema: {path}"
            ) from exc

    @staticmethod
    def _build_history(
        *,
        history_id: str,
        source_catalog_dir: str,
        policy: RecoveryBenchmarkQualityGatePolicy,
        gate_results: list[RecoveryBenchmarkQualityGateResult],
        entries: list[RecoveryBenchmarkComparisonHistoryEntry],
        violations: list[RecoveryBenchmarkQualityGateViolation],
        summary: str,
    ) -> RecoveryBenchmarkComparisonHistory:
        decision = (
            RecoveryBenchmarkQualityGateDecision.FAILED
            if not gate_results
            else RecoveryBenchmarkComparisonHistoryService._aggregate_decision(
                [item.decision for item in gate_results]
            )
        )
        return RecoveryBenchmarkComparisonHistory(
            history_id=history_id,
            source_catalog_dir=source_catalog_dir,
            policy=policy,
            overall_decision=decision,
            evaluated_comparisons=len(gate_results),
            passed_comparisons=sum(
                1
                for item in gate_results
                if item.decision == RecoveryBenchmarkQualityGateDecision.PASSED
            ),
            warning_comparisons=sum(
                1
                for item in gate_results
                if item.decision == RecoveryBenchmarkQualityGateDecision.WARNING
            ),
            failed_comparisons=sum(
                1
                for item in gate_results
                if item.decision == RecoveryBenchmarkQualityGateDecision.FAILED
            ),
            entries=entries,
            violations=violations,
            summary=summary,
        )

    @staticmethod
    def _build_catalog_entry(
        *,
        history: RecoveryBenchmarkComparisonHistory,
        path: Path,
    ) -> RecoveryBenchmarkComparisonHistoryCatalogEntry:
        return RecoveryBenchmarkComparisonHistoryCatalogEntry(
            history_id=history.history_id,
            source_catalog_dir=history.source_catalog_dir,
            overall_decision=history.overall_decision,
            evaluated_comparisons=history.evaluated_comparisons,
            passed_comparisons=history.passed_comparisons,
            warning_comparisons=history.warning_comparisons,
            failed_comparisons=history.failed_comparisons,
            path=str(path),
            summary=history.summary,
        )

    @staticmethod
    def _aggregate_decision(
        decisions: list[RecoveryBenchmarkQualityGateDecision],
    ) -> RecoveryBenchmarkQualityGateDecision:
        if RecoveryBenchmarkQualityGateDecision.FAILED in decisions:
            return RecoveryBenchmarkQualityGateDecision.FAILED
        if RecoveryBenchmarkQualityGateDecision.WARNING in decisions:
            return RecoveryBenchmarkQualityGateDecision.WARNING
        return RecoveryBenchmarkQualityGateDecision.PASSED

    @staticmethod
    def _history_id(
        *,
        source_catalog_dir: str,
        policy: RecoveryBenchmarkQualityGatePolicy,
    ) -> str:
        policy_id = "fail-on-mixed" if policy.fail_on_mixed else "default"
        return (
            "comparison-history:"
            f"{RecoveryBenchmarkComparisonHistoryService._safe_path_id(source_catalog_dir)}:"
            f"{policy_id}"
        )

    @staticmethod
    def _safe_path_id(path: str) -> str:
        return str(Path(path).resolve()).replace("\\", "/").replace("/", "__")

    @staticmethod
    def _catalog_path(directory: Path, history_id: str) -> Path:
        encoded_history_id = quote(history_id, safe="-_")
        if len(encoded_history_id) > 120:
            digest = sha256(history_id.encode("utf-8")).hexdigest()
            encoded_history_id = f"comparison-history-{digest}"
        return directory / f"{encoded_history_id}.json"
