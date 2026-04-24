from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from tests.artifacts import artifact_dir

from mobiflow_agent.common.contracts import EntityKind, EvidenceKind, EvidenceRef, VerificationStatus, VerificationVerdict
from mobiflow_agent.execution.recovery.execution import GovernedRecoveryExecutionResponse
from mobiflow_agent.memory.catalog import MemoryCasePersistenceService
from mobiflow_agent.memory.quality import MemoryCaseQualityDecision
from mobiflow_agent.memory.case import MemoryCaseRetrievalService
from mobiflow_agent.memory.embedding import MemoryEmbeddingAssetService
from mobiflow_agent.memory.vector import (
    MemoryVectorAdapterSchemaVersion,
    MemoryVectorCatalogIndexResult,
    MemoryVectorQueryRequest,
    MemoryVectorQueryResult,
    MemoryVectorRecord,
)
from mobiflow_agent.memory.vector import MemoryVectorAdapterService
from mobiflow_agent.execution.followup.driver import RecoveryFollowupDriverDecision
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
    case_id: str,
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
    case_id: str,
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
    with_eval_case: bool = True,
):
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


def _embedding_asset(
    *,
    case_id: str,
    source: str = "catalog",
    category: str = "followup",
    action_name: str = "create_run",
    input_summary: str | None = None,
    tags: list[str] | None = None,
):
    case = _memory_case(
        case_id=case_id,
        source=source,
        category=category,
        action_name=action_name,
        input_summary=input_summary,
        tags=tags,
        with_eval_case=True,
    )
    return MemoryEmbeddingAssetService().build_asset(case)


def _test_dir(artifact_tmp_path: Path, name: str) -> Path:
    return artifact_dir(artifact_tmp_path, name)


def _save_embedding_assets(catalog_dir: Path, case_ids: list[str]) -> None:
    persistence = MemoryCasePersistenceService()
    embedding_service = MemoryEmbeddingAssetService()
    for case_id in case_ids:
        case = _memory_case(case_id=case_id, tags=["priority", "device"], with_eval_case=True)
        persistence.save_to_catalog(case=case, catalog_dir=str(catalog_dir / "memory"))
        asset = embedding_service.build_asset(case)
        embedding_service.save_to_catalog(asset, str(catalog_dir))


def test_upsert_asset_builds_traceable_record() -> None:
    service = MemoryVectorAdapterService()
    asset = _embedding_asset(case_id="memory:a", source="manual", category="device-recovery", tags=["device", "priority"])

    result = service.upsert_asset(asset)
    record = service.get_record("memory:a")

    assert result.case_id == "memory:a"
    assert result.replaced_existing is False
    assert result.record_count == 1
    assert record is not None
    assert record.case_id == "memory:a"
    assert record.source == "manual"
    assert record.category == "device-recovery"
    assert record.quality_decision in {MemoryCaseQualityDecision.PASSED, MemoryCaseQualityDecision.WARNING}
    assert "source: manual" in record.embedding_text


def test_upsert_asset_replaces_existing_record_without_duplication() -> None:
    service = MemoryVectorAdapterService()
    first = _embedding_asset(case_id="memory:a", input_summary="first summary", tags=["priority"])
    second = _embedding_asset(case_id="memory:a", input_summary="second summary", tags=["priority", "device"])

    service.upsert_asset(first)
    result = service.upsert_asset(second)
    record = service.get_record("memory:a")

    assert result.replaced_existing is True
    assert result.record_count == 1
    assert record is not None
    assert record.summary == "second summary"
    assert record.tags == ["priority", "device"]


def test_upsert_catalog_indexes_embedding_catalog_and_returns_stats(artifact_tmp_path) -> None:
    catalog_dir = _test_dir(artifact_tmp_path, "upsert-catalog")
    _save_embedding_assets(catalog_dir, ["memory:b", "memory:a"])

    result = MemoryVectorAdapterService().upsert_catalog(str(catalog_dir))

    assert result.catalog_dir == str(catalog_dir)
    assert result.catalog_asset_count == 2
    assert result.indexed_records == 2
    assert result.skipped_records == 0
    assert [item.case_id for item in result.upserts] == ["memory:a", "memory:b"]


def test_get_record_returns_none_for_unknown_case_id() -> None:
    service = MemoryVectorAdapterService()

    assert service.get_record("missing") is None


def test_query_uses_deterministic_token_overlap_and_stable_sorting() -> None:
    service = MemoryVectorAdapterService()
    service.upsert_asset(_embedding_asset(case_id="memory:b", tags=["priority"]))
    service.upsert_asset(_embedding_asset(case_id="memory:a", tags=["priority", "device"]))
    service.upsert_asset(_embedding_asset(case_id="memory:c", source="imported", action_name="cancel_run", tags=["skip"]))

    result = service.query(MemoryVectorQueryRequest(query_text="create_run priority device", limit=3))

    assert [match.record.case_id for match in result.matches] == ["memory:a", "memory:b"]
    assert result.matches[0].score == 3
    assert result.matches[0].matched_terms == ["create_run", "priority", "device"]
    assert result.matches[1].score == 2


def test_query_empty_query_text_returns_no_matches() -> None:
    service = MemoryVectorAdapterService()
    service.upsert_asset(_embedding_asset(case_id="memory:a", tags=["priority"]))

    result = service.query(MemoryVectorQueryRequest(query_text="   ", limit=3))

    assert result.matches == []
    assert result.indexed_record_count == 1
    assert result.summary == "Memory vector query requires non-empty query_text."


def test_query_on_empty_index_returns_no_matches() -> None:
    result = MemoryVectorAdapterService().query(MemoryVectorQueryRequest(query_text="create_run", limit=3))

    assert result.indexed_record_count == 0
    assert result.matches == []
    assert result.summary == "Memory vector adapter has no indexed records."


def test_query_limit_and_case_id_tiebreak_are_stable() -> None:
    service = MemoryVectorAdapterService()
    service.upsert_asset(_embedding_asset(case_id="memory:b", source="manual"))
    service.upsert_asset(_embedding_asset(case_id="memory:a", source="manual"))
    service.upsert_asset(_embedding_asset(case_id="memory:c", source="manual"))

    result = service.query(MemoryVectorQueryRequest(query_text="manual", limit=2))

    assert [match.record.case_id for match in result.matches] == ["memory:a", "memory:b"]
    assert all(match.score == 1 for match in result.matches)


def test_roundtrip_models_validate_cleanly() -> None:
    service = MemoryVectorAdapterService()
    asset = _embedding_asset(case_id="memory:roundtrip", tags=["priority", "device"])
    service.upsert_asset(asset)
    result = service.query(MemoryVectorQueryRequest(query_text="create_run device", limit=3))
    record = service.get_record("memory:roundtrip")

    assert record is not None
    record_roundtrip = MemoryVectorRecord.model_validate(record.model_dump(mode="json"))
    request_roundtrip = MemoryVectorQueryRequest.model_validate(result.query.model_dump(mode="json"))
    result_roundtrip = MemoryVectorQueryResult.model_validate(result.model_dump(mode="json"))
    index_roundtrip = MemoryVectorCatalogIndexResult.model_validate(
        MemoryVectorCatalogIndexResult(
            catalog_dir="catalog",
            catalog_asset_count=1,
            indexed_records=1,
            skipped_records=0,
            upserts=[],
            summary="indexed",
        ).model_dump(mode="json")
    )

    assert record_roundtrip.schema_version == MemoryVectorAdapterSchemaVersion.V1
    assert request_roundtrip.query_text == "create_run device"
    assert result_roundtrip.matches[0].record.case_id == "memory:roundtrip"
    assert index_roundtrip.indexed_records == 1


def test_upsert_catalog_missing_directory_raises_file_not_found() -> None:
    with pytest.raises(FileNotFoundError, match="Memory embedding catalog directory does not exist"):
        MemoryVectorAdapterService().upsert_catalog("missing-catalog")


def test_upsert_catalog_invalid_embedding_document_raises_value_error(artifact_tmp_path) -> None:
    catalog_dir = _test_dir(artifact_tmp_path, "invalid-catalog")
    (catalog_dir / "broken.json").write_text("{not-json", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid memory embedding JSON document"):
        MemoryVectorAdapterService().upsert_catalog(str(catalog_dir))


def test_clear_removes_indexed_records() -> None:
    service = MemoryVectorAdapterService()
    service.upsert_asset(_embedding_asset(case_id="memory:a", tags=["priority"]))

    service.clear()

    assert service.get_record("memory:a") is None
    result = service.query(MemoryVectorQueryRequest(query_text="priority"))
    assert result.indexed_record_count == 0


