from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from tests.artifacts import artifact_dir

from mobiflow_agent.common.contracts import EntityKind, EvidenceKind, EvidenceRef, VerificationStatus, VerificationVerdict
from mobiflow_agent.execution.recovery.execution import GovernedRecoveryExecutionResponse
from mobiflow_agent.memory.case import RecoveryCaseQuery, RecoveryMemoryCase
from mobiflow_agent.memory.catalog import MemoryCasePersistenceService
from mobiflow_agent.memory.case import MemoryCaseRetrievalService
from mobiflow_agent.memory.catalog import (
    MemoryCatalogFilter,
    MemoryCatalogRetrievalRequest,
    MemoryCatalogRetrievalResult,
)
from mobiflow_agent.memory.catalog import MemoryCatalogRetrievalService
from mobiflow_agent.memory.embedding import MemoryEmbeddingAssetService
from mobiflow_agent.memory.hybrid import (
    MemoryHybridRetrievalMatch,
    MemoryHybridRetrievalRequest,
    MemoryHybridRetrievalResult,
    MemoryHybridRetrievalSchemaVersion,
)
from mobiflow_agent.memory.hybrid import MemoryHybridRetrievalService
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


def _index_cases(vector_service: MemoryVectorAdapterService, cases: list[RecoveryMemoryCase]) -> None:
    embedding_service = MemoryEmbeddingAssetService()
    for case in cases:
        vector_service.upsert_asset(embedding_service.build_asset(case))


def test_preview_candidates_reuses_catalog_filter_behavior(artifact_tmp_path) -> None:
    catalog_dir = _test_dir(artifact_tmp_path, "preview")
    cases = [
        _memory_case(case_id="memory:b", source="imported", tags=["priority"]),
        _memory_case(case_id="memory:a", source="manual", tags=["priority", "device"]),
    ]
    _save_cases(catalog_dir, cases)
    filters = MemoryCatalogFilter(sources=["manual"], tags_all=["priority", "device"])

    hybrid = MemoryHybridRetrievalService().preview_candidates(str(catalog_dir), filters=filters)
    baseline = MemoryCatalogRetrievalService().preview_candidates(str(catalog_dir), filters=filters)

    assert hybrid.catalog_case_count == baseline.catalog_case_count
    assert hybrid.filtered_case_count == baseline.filtered_case_count
    assert hybrid.summary == baseline.summary


def test_retrieve_deterministic_only_matches_catalog_retrieval(artifact_tmp_path) -> None:
    catalog_dir = _test_dir(artifact_tmp_path, "deterministic-only")
    cases = [
        _memory_case(case_id="memory:b", tags=["priority"]),
        _memory_case(case_id="memory:a", tags=["priority", "device"]),
    ]
    _save_cases(catalog_dir, cases)
    request = MemoryHybridRetrievalRequest(
        query=RecoveryCaseQuery(action_name="create_run", tags=["priority", "device"], limit=3),
        limit=3,
    )

    result = MemoryHybridRetrievalService().retrieve(str(catalog_dir), request)
    baseline = MemoryCatalogRetrievalService().retrieve(
        str(catalog_dir),
        request=MemoryCatalogRetrievalRequest(query=RecoveryCaseQuery(action_name="create_run", tags=["priority", "device"], limit=3)),
    )

    assert [match.case.case_id for match in result.matches] == [match.case.case_id for match in baseline.matches]
    assert [match.combined_score for match in result.matches] == [match.score for match in baseline.matches]
    assert all(match.match_sources == ["deterministic"] for match in result.matches)


def test_retrieve_vector_only_returns_canonical_memory_cases(artifact_tmp_path) -> None:
    catalog_dir = _test_dir(artifact_tmp_path, "vector-only")
    vector_service = MemoryVectorAdapterService()
    cases = [
        _memory_case(case_id="memory:b", input_summary="follow summary", tags=["blocked"]),
        _memory_case(case_id="memory:a", input_summary="device recovery follow summary", tags=["device", "priority"]),
    ]
    _save_cases(catalog_dir, cases)
    _index_cases(vector_service, cases)
    service = MemoryHybridRetrievalService(vector_adapter_service=vector_service)

    result = service.retrieve(
        str(catalog_dir),
        MemoryHybridRetrievalRequest(
            query=RecoveryCaseQuery(),
            vector_query_text="device recovery priority",
            limit=3,
        ),
    )

    assert [match.case.case_id for match in result.matches] == ["memory:a"]
    assert result.matches[0].match_sources == ["vector"]
    assert result.matches[0].deterministic_score == 0
    assert result.matches[0].vector_score > 0
    assert result.matches[0].case.replay_case == cases[1].replay_case


def test_retrieve_merges_deterministic_and_vector_matches_by_case_id(artifact_tmp_path) -> None:
    catalog_dir = _test_dir(artifact_tmp_path, "merge")
    vector_service = MemoryVectorAdapterService()
    cases = [
        _memory_case(case_id="memory:a", input_summary="device recovery path", tags=["priority", "device"]),
        _memory_case(case_id="memory:b", input_summary="general path", tags=["priority"]),
    ]
    _save_cases(catalog_dir, cases)
    _index_cases(vector_service, cases)
    service = MemoryHybridRetrievalService(vector_adapter_service=vector_service)

    result = service.retrieve(
        str(catalog_dir),
        MemoryHybridRetrievalRequest(
            query=RecoveryCaseQuery(action_name="create_run", tags=["priority"], limit=5),
            vector_query_text="device recovery",
            limit=5,
        ),
    )

    merged = {match.case.case_id: match for match in result.matches}
    assert merged["memory:a"].match_sources == ["deterministic", "vector"]
    assert merged["memory:a"].combined_score == (
        merged["memory:a"].deterministic_score + merged["memory:a"].vector_score
    )
    assert merged["memory:b"].match_sources == ["deterministic"]


def test_prefer_vector_changes_only_same_score_tie_break(artifact_tmp_path) -> None:
    catalog_dir = _test_dir(artifact_tmp_path, "prefer-vector")
    vector_service = MemoryVectorAdapterService()
    cases = [
        _memory_case(case_id="memory:a", source="manual", input_summary="basic note", tags=["priority"]),
        _memory_case(case_id="memory:b", source="manual", input_summary="extra detail", tags=[]),
    ]
    _save_cases(catalog_dir, cases)
    _index_cases(vector_service, cases)
    service = MemoryHybridRetrievalService(vector_adapter_service=vector_service)
    request = MemoryHybridRetrievalRequest(
        query=RecoveryCaseQuery(action_name="create_run", tags=["priority"], limit=5),
        vector_query_text="manual extra",
        limit=5,
    )

    default_result = service.retrieve(str(catalog_dir), request)
    vector_preferred_result = service.retrieve(
        str(catalog_dir),
        request.model_copy(update={"prefer_vector": True}),
    )

    assert [match.case.case_id for match in default_result.matches[:2]] == ["memory:a", "memory:b"]
    assert [match.case.case_id for match in vector_preferred_result.matches[:2]] == ["memory:b", "memory:a"]
    assert default_result.matches[0].combined_score == vector_preferred_result.matches[0].combined_score


def test_vector_query_text_empty_uses_only_deterministic_channel(artifact_tmp_path) -> None:
    catalog_dir = _test_dir(artifact_tmp_path, "empty-vector")
    vector_service = MemoryVectorAdapterService()
    cases = [_memory_case(case_id="memory:a", tags=["priority", "device"])]
    _save_cases(catalog_dir, cases)
    _index_cases(vector_service, cases)
    service = MemoryHybridRetrievalService(vector_adapter_service=vector_service)

    result = service.retrieve(
        str(catalog_dir),
        MemoryHybridRetrievalRequest(
            query=RecoveryCaseQuery(action_name="create_run", tags=["priority"]),
            vector_query_text="   ",
            limit=3,
        ),
    )

    assert len(result.matches) == 1
    assert result.matches[0].match_sources == ["deterministic"]
    assert result.matches[0].vector_score == 0


def test_both_query_channels_empty_returns_no_matches(artifact_tmp_path) -> None:
    catalog_dir = _test_dir(artifact_tmp_path, "empty-request")
    _save_cases(catalog_dir, [_memory_case(case_id="memory:a", tags=["priority"])])

    result = MemoryHybridRetrievalService().retrieve(
        str(catalog_dir),
        MemoryHybridRetrievalRequest(
            query=RecoveryCaseQuery(),
            vector_query_text=None,
            limit=3,
        ),
    )

    assert result.matches == []
    assert "requires deterministic query filters or vector_query_text" in result.summary


def test_empty_vector_index_falls_back_to_deterministic_without_error(artifact_tmp_path) -> None:
    catalog_dir = _test_dir(artifact_tmp_path, "vector-fallback")
    cases = [_memory_case(case_id="memory:a", tags=["priority", "device"])]
    _save_cases(catalog_dir, cases)
    service = MemoryHybridRetrievalService(vector_adapter_service=MemoryVectorAdapterService())

    result = service.retrieve(
        str(catalog_dir),
        MemoryHybridRetrievalRequest(
            query=RecoveryCaseQuery(action_name="create_run", tags=["priority"]),
            vector_query_text="device priority",
            limit=3,
        ),
    )

    assert len(result.matches) == 1
    assert result.matches[0].match_sources == ["deterministic"]


def test_empty_catalog_returns_no_candidate_evidence(artifact_tmp_path) -> None:
    catalog_dir = _test_dir(artifact_tmp_path, "empty-catalog")

    result = MemoryHybridRetrievalService().retrieve(
        str(catalog_dir),
        MemoryHybridRetrievalRequest(
            query=RecoveryCaseQuery(action_name="create_run"),
            vector_query_text="device",
            limit=3,
        ),
    )

    assert result.catalog_case_count == 0
    assert result.filtered_case_count == 0
    assert result.matches == []
    assert "no candidate evidence" in result.summary


def test_assets_support_roundtrip() -> None:
    case = _memory_case(case_id="memory:roundtrip", tags=["priority"])
    request = MemoryHybridRetrievalRequest(
        query=RecoveryCaseQuery(action_name="create_run"),
        vector_query_text="priority",
        filters=MemoryCatalogFilter(tags_all=["priority"]),
        limit=3,
        prefer_vector=True,
    )
    match = MemoryHybridRetrievalMatch(
        case=case,
        combined_score=6,
        deterministic_score=4,
        vector_score=2,
        match_sources=["deterministic", "vector"],
        summary="roundtrip",
    )
    result = MemoryHybridRetrievalResult(
        catalog_dir="catalog",
        catalog_case_count=2,
        filtered_case_count=1,
        request=request,
        matches=[match],
        summary="roundtrip result",
    )

    restored_request = MemoryHybridRetrievalRequest.model_validate(request.model_dump(mode="json"))
    restored_match = MemoryHybridRetrievalMatch.model_validate(match.model_dump(mode="json"))
    restored_result = MemoryHybridRetrievalResult.model_validate(result.model_dump(mode="json"))

    assert restored_request.schema_version == MemoryHybridRetrievalSchemaVersion.V1
    assert restored_request.prefer_vector is True
    assert restored_match.match_sources == ["deterministic", "vector"]
    assert restored_result.matches[0].case.case_id == "memory:roundtrip"


def test_missing_memory_catalog_directory_raises_file_not_found(artifact_tmp_path) -> None:
    missing_dir = _test_dir(artifact_tmp_path, "missing").parent / f"missing-{uuid4().hex}"

    with pytest.raises(FileNotFoundError, match="Memory case catalog directory does not exist"):
        MemoryHybridRetrievalService().retrieve(
            str(missing_dir),
            MemoryHybridRetrievalRequest(query=RecoveryCaseQuery(action_name="create_run")),
        )


def test_invalid_memory_document_errors_are_owned_by_persistence_layer(artifact_tmp_path) -> None:
    catalog_dir = _test_dir(artifact_tmp_path, "invalid-memory")
    (catalog_dir / "broken.json").write_text(
        json.dumps({"schema_version": "v1", "case": {"oops": True}}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Invalid memory case document schema"):
        MemoryHybridRetrievalService().retrieve(
            str(catalog_dir),
            MemoryHybridRetrievalRequest(query=RecoveryCaseQuery(action_name="create_run")),
        )


def test_invalid_embedding_document_errors_remain_owned_by_vector_persistence_layer(artifact_tmp_path) -> None:
    catalog_dir = _test_dir(artifact_tmp_path, "invalid-embedding")
    (catalog_dir / "broken.json").write_text("{not-json", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid memory embedding JSON document"):
        MemoryVectorAdapterService().upsert_catalog(str(catalog_dir))


