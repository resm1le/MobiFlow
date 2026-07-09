from __future__ import annotations

"""Memory embedding assets and service."""

from enum import Enum

from pydantic import Field

from mobiflow_agent.common.contracts import StrictModel, VerificationStatus
from mobiflow_agent.memory.quality import MemoryCaseQualityDecision
from mobiflow_agent.execution.followup.decisions import RecoveryFollowupDriverDecision

class MemoryEmbeddingAssetSchemaVersion(str, Enum):
    V1 = "v1"

class RecoveryMemoryEmbeddingAsset(StrictModel):
    schema_version: MemoryEmbeddingAssetSchemaVersion = MemoryEmbeddingAssetSchemaVersion.V1
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

class RecoveryMemoryEmbeddingDocument(StrictModel):
    schema_version: MemoryEmbeddingAssetSchemaVersion = MemoryEmbeddingAssetSchemaVersion.V1
    asset: RecoveryMemoryEmbeddingAsset

class RecoveryMemoryEmbeddingCatalogEntry(StrictModel):
    case_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    category: str = Field(min_length=1)
    action_name: str = Field(min_length=1)
    decision: RecoveryFollowupDriverDecision
    verdict_status: VerificationStatus | None = None
    tags: list[str] = Field(default_factory=list)
    quality_decision: MemoryCaseQualityDecision
    quality_issue_count: int = Field(ge=0)
    path: str = Field(min_length=1)
    summary: str = Field(min_length=1)

class RecoveryMemoryEmbeddingCatalog(StrictModel):
    schema_version: MemoryEmbeddingAssetSchemaVersion = MemoryEmbeddingAssetSchemaVersion.V1
    catalog_dir: str = Field(min_length=1)
    entries: list[RecoveryMemoryEmbeddingCatalogEntry] = Field(default_factory=list)
    summary: str = Field(min_length=1)

import json
from hashlib import sha256
from pathlib import Path
from urllib.parse import quote

from pydantic import ValidationError

from mobiflow_agent.memory.case import RecoveryMemoryCase
from mobiflow_agent.memory.catalog import MemoryCasePersistenceService
from mobiflow_agent.memory.quality import MemoryCaseQualityDecision, MemoryCaseQualityPolicy
from mobiflow_agent.memory.quality import MemoryCaseQualityService
class MemoryEmbeddingAssetService:
    def __init__(
        self,
        *,
        persistence_service: MemoryCasePersistenceService | None = None,
        quality_service: MemoryCaseQualityService | None = None,
    ) -> None:
        self._persistence_service = persistence_service or MemoryCasePersistenceService()
        self._quality_service = quality_service or MemoryCaseQualityService(
            persistence_service=self._persistence_service
        )

    def build_asset(
        self,
        case: RecoveryMemoryCase,
        *,
        quality_policy: MemoryCaseQualityPolicy | None = None,
    ) -> RecoveryMemoryEmbeddingAsset:
        assessment = self._quality_service.assess_case(case, policy=quality_policy)
        preview = assessment.normalization_preview
        if assessment.decision == MemoryCaseQualityDecision.FAILED:
            raise ValueError(
                f"Memory case {case.case_id} failed quality assessment and cannot build an embedding asset."
            )

        embedding_text = self._embedding_text(
            source=preview.normalized_source,
            category=preview.normalized_category,
            action_name=preview.normalized_action_name,
            decision=case.decision.value,
            verdict_status=case.verdict_status.value if case.verdict_status is not None else "none",
            tags=preview.normalized_tags,
            input_summary=preview.normalized_input_summary,
        )
        return RecoveryMemoryEmbeddingAsset(
            case_id=case.case_id,
            source=preview.normalized_source,
            category=preview.normalized_category,
            action_name=preview.normalized_action_name,
            decision=case.decision,
            verdict_status=case.verdict_status,
            tags=preview.normalized_tags,
            quality_decision=assessment.decision,
            quality_issue_count=assessment.issue_count,
            embedding_text=embedding_text,
            summary=preview.normalized_input_summary,
        )

    def build_asset_from_catalog(
        self,
        catalog_dir: str,
        *,
        case_id: str,
        quality_policy: MemoryCaseQualityPolicy | None = None,
    ) -> RecoveryMemoryEmbeddingAsset:
        case = self._persistence_service.load_from_catalog(catalog_dir=catalog_dir, case_id=case_id)
        return self.build_asset(case, quality_policy=quality_policy)

    def save_asset(
        self,
        asset: RecoveryMemoryEmbeddingAsset,
        output_path: str,
    ) -> RecoveryMemoryEmbeddingCatalogEntry:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        document = RecoveryMemoryEmbeddingDocument(asset=asset)
        payload = document.model_dump(mode="json")
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return self._build_catalog_entry(asset=asset, path=path)

    def load_asset(self, path: str) -> RecoveryMemoryEmbeddingAsset:
        return self._load_document(Path(path)).asset

    def save_to_catalog(
        self,
        asset: RecoveryMemoryEmbeddingAsset,
        catalog_dir: str,
    ) -> RecoveryMemoryEmbeddingCatalogEntry:
        path = self._catalog_path(Path(catalog_dir), asset.case_id)
        return self.save_asset(asset, str(path))

    def list_catalog(self, catalog_dir: str) -> RecoveryMemoryEmbeddingCatalog:
        directory = Path(catalog_dir)
        if not directory.exists():
            raise FileNotFoundError(f"Memory embedding catalog directory does not exist: {directory}")

        entries = [
            self._build_catalog_entry(asset=document.asset, path=path)
            for path, document in self._iter_catalog_documents(directory)
        ]
        entries.sort(key=lambda item: item.case_id)
        return RecoveryMemoryEmbeddingCatalog(
            catalog_dir=str(directory),
            entries=entries,
            summary=f"Memory embedding catalog {directory} contains {len(entries)} assets.",
        )

    def load_from_catalog(
        self,
        *,
        catalog_dir: str,
        case_id: str,
    ) -> RecoveryMemoryEmbeddingAsset:
        return self.load_asset(str(self._catalog_path(Path(catalog_dir), case_id)))

    def _iter_catalog_documents(
        self,
        directory: Path,
    ) -> list[tuple[Path, RecoveryMemoryEmbeddingDocument]]:
        documents: list[tuple[Path, RecoveryMemoryEmbeddingDocument]] = []
        for path in sorted(directory.glob("*.json"), key=lambda item: item.name):
            documents.append((path, self._load_document(path)))
        return documents

    @staticmethod
    def _load_document(path: Path) -> RecoveryMemoryEmbeddingDocument:
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid memory embedding JSON document: {path}") from exc
        try:
            return RecoveryMemoryEmbeddingDocument.model_validate(payload)
        except ValidationError as exc:
            raise ValueError(f"Invalid memory embedding document schema: {path}") from exc

    @staticmethod
    def _build_catalog_entry(
        *,
        asset: RecoveryMemoryEmbeddingAsset,
        path: Path,
    ) -> RecoveryMemoryEmbeddingCatalogEntry:
        return RecoveryMemoryEmbeddingCatalogEntry(
            case_id=asset.case_id,
            source=asset.source,
            category=asset.category,
            action_name=asset.action_name,
            decision=asset.decision,
            verdict_status=asset.verdict_status,
            tags=asset.tags,
            quality_decision=asset.quality_decision,
            quality_issue_count=asset.quality_issue_count,
            path=str(path),
            summary=asset.summary,
        )

    @staticmethod
    def _catalog_path(directory: Path, case_id: str) -> Path:
        encoded_case_id = quote(case_id, safe="-_")
        if len(encoded_case_id) > 120:
            digest = sha256(case_id.encode("utf-8")).hexdigest()
            encoded_case_id = f"memory-embedding-{digest}"
        return directory / f"{encoded_case_id}.json"

    @staticmethod
    def _embedding_text(
        *,
        source: str,
        category: str,
        action_name: str,
        decision: str,
        verdict_status: str,
        tags: list[str],
        input_summary: str,
    ) -> str:
        rendered_tags = ", ".join(tags) if tags else "(none)"
        return "\n".join(
            [
                f"source: {source}",
                f"category: {category}",
                f"action_name: {action_name}",
                f"decision: {decision}",
                f"verdict_status: {verdict_status}",
                f"tags: {rendered_tags}",
                f"input_summary: {input_summary}",
            ]
        )
