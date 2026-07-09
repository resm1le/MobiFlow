from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from tests.artifacts import artifact_dir

from mobiflow_agent.common.contracts import EntityKind, EvidenceKind, EvidenceRef, VerificationStatus, VerificationVerdict
from mobiflow_agent.execution.recovery.execution import GovernedRecoveryExecutionResponse
from mobiflow_agent.memory.case import RecoveryMemoryCase
from mobiflow_agent.memory.catalog import MemoryCasePersistenceService
from mobiflow_agent.memory.quality import MemoryCaseQualityDecision, MemoryCaseQualityPolicy
from mobiflow_agent.memory.case import MemoryCaseRetrievalService
from mobiflow_agent.memory.embedding import (
    MemoryEmbeddingAssetSchemaVersion,
    RecoveryMemoryEmbeddingAsset,
    RecoveryMemoryEmbeddingCatalog,
    RecoveryMemoryEmbeddingCatalogEntry,
    RecoveryMemoryEmbeddingDocument,
)
from mobiflow_agent.memory.embedding import MemoryEmbeddingAssetService
from mobiflow_agent.execution.followup.decisions import RecoveryFollowupDriverDecision
from tests.harness_helpers import build_task_harness_response
from mobiflow_agent.evaluation.replay import RecoveryEvalCase, RecoveryReplayCase
from mobiflow_agent.runtime.state import AgentRuntimeState, RuntimeLifecycle


def _verdict(status: VerificationStatus, *, summary: str = "completed") -> VerificationVerdict:
    evidence = [
        EvidenceRef(
            evidence_id="snapshot:test:run:rt-1",
            kind=EvidenceKind.PLATFORM_SNAPSHOT,
            summary="test snapshot",
            locator="rt-1",
        )
    ]
    return VerificationVerdict(
        verdict_id=f"verdict:{status.value}",
        status=status,
        summary=summary,
        target_kind=EntityKind.RUN_TARGET,
        target_id="rt-1",
        evidence_refs=evidence if status in {VerificationStatus.VERIFIED_SUCCESS, VerificationStatus.VERIFIED_FAILED} else [],
        blocked_reason="blocked_by_policy" if status == VerificationStatus.BLOCKED else None,
    )


def _execution_response(
    *,
    action_name: str = "create_run",
    created_run_id: str | None = "run-created",
    followup_required: bool = True,
    verdict_status: VerificationStatus = VerificationStatus.VERIFIED_SUCCESS,
) -> GovernedRecoveryExecutionResponse:
    verdict = _verdict(verdict_status, summary=f"{action_name} completed")
    return GovernedRecoveryExecutionResponse(
        thread_id="thread-1",
        run_target_id="rt-1",
        run_id="run-1",
        action_name=action_name,
        created_run_id=created_run_id,
        followup_required=followup_required,
        lifecycle=RuntimeLifecycle.COMPLETED,
        verdict=verdict,
        approval_request=None,
        runtime_state=AgentRuntimeState(
            session_id="session-1",
            lifecycle=RuntimeLifecycle.COMPLETED,
            latest_verdict=verdict,
        ),
    )


def _harness_response(
    *,
    decision: RecoveryFollowupDriverDecision = RecoveryFollowupDriverDecision.COMPLETE,
    verdict_status: VerificationStatus | None = VerificationStatus.VERIFIED_SUCCESS,
):
    verdict = _verdict(verdict_status, summary="followup assessed") if verdict_status is not None else None
    return build_task_harness_response(decision=decision, verdict=verdict)


def _replay_case(
    *,
    case_id: str = "replay:test",
    action_name: str = "create_run",
    decision: RecoveryFollowupDriverDecision = RecoveryFollowupDriverDecision.COMPLETE,
    verdict_status: VerificationStatus | None = VerificationStatus.VERIFIED_SUCCESS,
) -> RecoveryReplayCase:
    return RecoveryReplayCase(
        case_id=case_id,
        source="test-source",
        execution=_execution_response(action_name=action_name),
        harness_response=_harness_response(decision=decision, verdict_status=verdict_status),
    )


def _eval_case(
    replay_case: RecoveryReplayCase,
    *,
    case_id: str = "eval:test",
    category: str = "followup",
    input_summary: str = "eval summary",
) -> RecoveryEvalCase:
    return RecoveryEvalCase(
        case_id=case_id,
        category=category,
        input_summary=input_summary,
        expected_decision=replay_case.harness_response.decision,
        expected_verdict_status=MemoryCaseRetrievalService._extract_verdict_status(replay_case.harness_response),
        replay_case=replay_case,
    )


def _memory_case(
    *,
    case_id: str,
    source: str = "catalog",
    category: str = "followup",
    action_name: str = "create_run",
    decision: RecoveryFollowupDriverDecision = RecoveryFollowupDriverDecision.COMPLETE,
    verdict_status: VerificationStatus | None = VerificationStatus.VERIFIED_SUCCESS,
    input_summary: str | None = None,
    tags: list[str] | None = None,
    with_eval_case: bool = False,
) -> RecoveryMemoryCase:
    replay_case = _replay_case(
        case_id=f"replay:{case_id}",
        action_name=action_name,
        decision=decision,
        verdict_status=verdict_status,
    )
    eval_case = _eval_case(replay_case, case_id=f"eval:{case_id}", category=category) if with_eval_case else None
    case = MemoryCaseRetrievalService().build_case(
        source=source,
        replay_case=replay_case,
        eval_case=eval_case,
        category=category,
        input_summary=input_summary or f"{case_id} summary",
        tags=tags,
    )
    return case.model_copy(update={"case_id": case_id})


def _test_dir(artifact_tmp_path: Path, name: str) -> Path:
    return artifact_dir(artifact_tmp_path, name)


def _save_cases(catalog_dir: Path, cases: list[RecoveryMemoryCase]) -> None:
    persistence = MemoryCasePersistenceService()
    for case in cases:
        persistence.save_to_catalog(case=case, catalog_dir=str(catalog_dir))


def test_build_asset_for_passed_case_uses_normalized_embedding_text() -> None:
    case = _memory_case(
        case_id="memory:passed",
        source=" catalog ",
        category=" followup ",
        action_name=" create_run ",
        input_summary="  useful summary  ",
        tags=[" verified ", "device", "verified"],
        with_eval_case=True,
    ).model_copy(
        update={
            "source": " catalog ",
            "category": " followup ",
            "action_name": " create_run ",
            "input_summary": "  useful summary  ",
            "tags": [" verified ", "device", "verified"],
        }
    )

    asset = MemoryEmbeddingAssetService().build_asset(case)

    assert asset.quality_decision == MemoryCaseQualityDecision.WARNING
    assert asset.quality_issue_count == 5
    assert asset.source == "catalog"
    assert asset.category == "followup"
    assert asset.action_name == "create_run"
    assert asset.tags == ["verified", "device"]
    assert asset.embedding_text == "\n".join(
        [
            "source: catalog",
            "category: followup",
            "action_name: create_run",
            f"decision: {RecoveryFollowupDriverDecision.COMPLETE.value}",
            f"verdict_status: {VerificationStatus.VERIFIED_SUCCESS.value}",
            "tags: verified, device",
            "input_summary: useful summary",
        ]
    )


def test_build_asset_for_warning_case_preserves_quality_metadata() -> None:
    case = _memory_case(case_id="memory:warning", input_summary="short")

    asset = MemoryEmbeddingAssetService().build_asset(case)

    assert asset.quality_decision == MemoryCaseQualityDecision.WARNING
    assert asset.quality_issue_count == 1
    assert asset.summary == "short"


def test_build_asset_for_failed_case_raises_value_error() -> None:
    case = _memory_case(case_id="memory:failed").model_copy(update={"action_name": "cancel_run"})

    with pytest.raises(ValueError, match="failed quality assessment"):
        MemoryEmbeddingAssetService().build_asset(case)


def test_build_asset_uses_normalized_fields_in_stable_order() -> None:
    case = _memory_case(
        case_id="memory:normalized-order",
        source="  manual  ",
        category="  recovery  ",
        input_summary="  condensed summary  ",
        tags=[" zeta ", "alpha", "alpha", ""],
    ).model_copy(
        update={
            "source": "  manual  ",
            "category": "  recovery  ",
            "input_summary": "  condensed summary  ",
            "tags": [" zeta ", "alpha", "alpha", ""],
        }
    )

    asset = MemoryEmbeddingAssetService().build_asset(case)

    assert asset.embedding_text.splitlines() == [
        "source: manual",
        "category: recovery",
        "action_name: create_run",
        f"decision: {RecoveryFollowupDriverDecision.COMPLETE.value}",
        f"verdict_status: {VerificationStatus.VERIFIED_SUCCESS.value}",
        "tags: zeta, alpha",
        "input_summary: condensed summary",
    ]


def test_build_asset_from_catalog_reads_selected_case(artifact_tmp_path) -> None:
    catalog_dir = _test_dir(artifact_tmp_path, "build-from-catalog")
    cases = [
        _memory_case(case_id="memory:b", input_summary="beta summary"),
        _memory_case(case_id="memory:a", input_summary="alpha summary"),
    ]
    _save_cases(catalog_dir, cases)

    asset = MemoryEmbeddingAssetService().build_asset_from_catalog(
        str(catalog_dir),
        case_id="memory:a",
    )

    assert asset.case_id == "memory:a"
    assert asset.summary == "alpha summary"


def test_save_asset_writes_utf8_json_document(artifact_tmp_path) -> None:
    service = MemoryEmbeddingAssetService()
    asset = service.build_asset(_memory_case(case_id="memory:save", input_summary="save summary"))
    output_path = _test_dir(artifact_tmp_path, "save-asset") / "nested" / "asset.json"

    entry = service.save_asset(asset, str(output_path))

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == MemoryEmbeddingAssetSchemaVersion.V1.value
    assert payload["asset"]["case_id"] == "memory:save"
    assert entry.case_id == "memory:save"
    assert entry.summary == "save summary"


def test_load_asset_restores_embedding_asset(artifact_tmp_path) -> None:
    service = MemoryEmbeddingAssetService()
    asset = service.build_asset(_memory_case(case_id="memory:load", input_summary="load summary"))
    output_path = _test_dir(artifact_tmp_path, "load-asset") / "asset.json"
    service.save_asset(asset, str(output_path))

    restored = service.load_asset(str(output_path))

    assert restored.case_id == asset.case_id
    assert restored.embedding_text == asset.embedding_text
    assert restored.summary == "load summary"


def test_document_and_catalog_entry_support_roundtrip() -> None:
    asset = MemoryEmbeddingAssetService().build_asset(
        _memory_case(case_id="memory:roundtrip", input_summary="roundtrip summary")
    )
    document = RecoveryMemoryEmbeddingDocument(asset=asset)
    entry = RecoveryMemoryEmbeddingCatalogEntry(
        case_id=asset.case_id,
        source=asset.source,
        category=asset.category,
        action_name=asset.action_name,
        decision=asset.decision,
        verdict_status=asset.verdict_status,
        tags=asset.tags,
        quality_decision=asset.quality_decision,
        quality_issue_count=asset.quality_issue_count,
        path="memory%3Aroundtrip.json",
        summary=asset.summary,
    )

    restored_document = RecoveryMemoryEmbeddingDocument.model_validate(document.model_dump(mode="python"))
    restored_entry = RecoveryMemoryEmbeddingCatalogEntry.model_validate(entry.model_dump(mode="python"))

    assert restored_document.schema_version == MemoryEmbeddingAssetSchemaVersion.V1
    assert restored_document.asset.case_id == "memory:roundtrip"
    assert restored_entry.case_id == "memory:roundtrip"
    assert restored_entry.summary == "roundtrip summary"


def test_save_to_catalog_list_catalog_and_load_from_catalog_are_stable(artifact_tmp_path) -> None:
    service = MemoryEmbeddingAssetService()
    catalog_dir = _test_dir(artifact_tmp_path, "catalog")
    asset_b = service.build_asset(_memory_case(case_id="memory:b", input_summary="beta"))
    asset_a = service.build_asset(_memory_case(case_id="memory:a", input_summary="alpha"))
    service.save_to_catalog(asset_b, str(catalog_dir))
    service.save_to_catalog(asset_a, str(catalog_dir))

    catalog = service.list_catalog(str(catalog_dir))
    restored = service.load_from_catalog(catalog_dir=str(catalog_dir), case_id="memory:a")

    assert isinstance(catalog, RecoveryMemoryEmbeddingCatalog)
    assert [entry.case_id for entry in catalog.entries] == ["memory:a", "memory:b"]
    assert restored.case_id == "memory:a"
    assert restored.summary == "alpha"


def test_empty_embedding_catalog_lists_empty_entries(artifact_tmp_path) -> None:
    catalog_dir = _test_dir(artifact_tmp_path, "empty")

    catalog = MemoryEmbeddingAssetService().list_catalog(str(catalog_dir))

    assert catalog.entries == []
    assert "contains 0 assets" in catalog.summary


def test_missing_embedding_catalog_directory_raises_file_not_found(artifact_tmp_path) -> None:
    missing_dir = _test_dir(artifact_tmp_path, "missing").parent / f"missing-{uuid4().hex}"

    with pytest.raises(FileNotFoundError, match="Memory embedding catalog directory does not exist"):
        MemoryEmbeddingAssetService().list_catalog(str(missing_dir))


def test_invalid_embedding_json_document_raises_value_error(artifact_tmp_path) -> None:
    path = _test_dir(artifact_tmp_path, "bad-json") / "broken.json"
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid memory embedding JSON document"):
        MemoryEmbeddingAssetService().load_asset(str(path))


def test_invalid_embedding_document_schema_raises_value_error(artifact_tmp_path) -> None:
    path = _test_dir(artifact_tmp_path, "bad-schema") / "broken.json"
    path.write_text(
        json.dumps({"schema_version": "v999", "asset": {"oops": True}}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Invalid memory embedding document schema"):
        MemoryEmbeddingAssetService().load_asset(str(path))


def test_embedding_service_is_static_and_does_not_require_provider_or_vector_store() -> None:
    service = MemoryEmbeddingAssetService()
    case = _memory_case(case_id="memory:static", input_summary="static summary")

    asset = service.build_asset(case, quality_policy=MemoryCaseQualityPolicy())

    assert isinstance(asset, RecoveryMemoryEmbeddingAsset)
    assert asset.case_id == "memory:static"
    assert "input_summary: static summary" in asset.embedding_text


