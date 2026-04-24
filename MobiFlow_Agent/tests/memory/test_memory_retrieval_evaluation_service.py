from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from tests.artifacts import artifact_dir

from mobiflow_agent.common.contracts import (
    EntityKind,
    EvidenceKind,
    EvidenceRef,
    VerificationStatus,
    VerificationVerdict,
)
from mobiflow_agent.execution.recovery.execution import (
    GovernedRecoveryExecutionResponse,
)
from mobiflow_agent.memory.case import RecoveryCaseQuery, RecoveryMemoryCase
from mobiflow_agent.memory.catalog import MemoryCasePersistenceService
from mobiflow_agent.memory.case import MemoryCaseRetrievalService
from mobiflow_agent.memory.catalog import MemoryCatalogFilter
from mobiflow_agent.memory.embedding import MemoryEmbeddingAssetService
from mobiflow_agent.memory.evaluation import (
    MemoryRetrievalEvaluationCase,
    MemoryRetrievalEvaluationCatalog,
    MemoryRetrievalEvaluationChannel,
    MemoryRetrievalEvaluationChannelResult,
    MemoryRetrievalEvaluationDecision,
    MemoryRetrievalEvaluationDocument,
    MemoryRetrievalEvaluationResult,
    MemoryRetrievalEvaluationSchemaVersion,
)
from mobiflow_agent.memory.evaluation import (
    MemoryRetrievalEvaluationService,
)
from mobiflow_agent.execution.followup.driver import (
    RecoveryFollowupDriverDecision,
)
from tests.harness_helpers import build_task_harness_response
from mobiflow_agent.evaluation.replay import RecoveryEvalCase, RecoveryReplayCase
from mobiflow_agent.runtime.state import AgentRuntimeState, RuntimeLifecycle


def _verdict(
    status: VerificationStatus,
    *,
    summary: str = "completed",
) -> VerificationVerdict:
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
        evidence_refs=(
            evidence
            if status
            in {
                VerificationStatus.VERIFIED_SUCCESS,
                VerificationStatus.VERIFIED_FAILED,
            }
            else []
        ),
        blocked_reason="blocked_by_policy"
        if status == VerificationStatus.BLOCKED
        else None,
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
        harness_response=_harness_response(
            decision=decision,
            verdict_status=verdict_status,
        ),
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
        expected_verdict_status=MemoryCaseRetrievalService._extract_verdict_status(
            replay_case.harness_response
        ),
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
    eval_case = (
        _eval_case(replay_case, case_id=f"eval:{case_id}", category=category)
        if with_eval_case
        else None
    )
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


def _save_embedding_assets(catalog_dir: Path, cases: list[RecoveryMemoryCase]) -> None:
    embedding_service = MemoryEmbeddingAssetService()
    for case in cases:
        asset = embedding_service.build_asset(case)
        embedding_service.save_to_catalog(asset, str(catalog_dir))


def _evaluation_case(
    *,
    evaluation_case_id: str = "eval-case:1",
    query: RecoveryCaseQuery | None = None,
    vector_query_text: str | None = None,
    filters: MemoryCatalogFilter | None = None,
    expected_case_ids: list[str] | None = None,
    limit: int = 5,
    summary: str = "evaluation summary",
) -> MemoryRetrievalEvaluationCase:
    return MemoryRetrievalEvaluationCase(
        evaluation_case_id=evaluation_case_id,
        query=query or RecoveryCaseQuery(),
        vector_query_text=vector_query_text,
        filters=filters,
        expected_case_ids=["memory:a"] if expected_case_ids is None else expected_case_ids,
        limit=limit,
        summary=summary,
    )


def test_evaluate_case_returns_deterministic_vector_and_hybrid_results(artifact_tmp_path) -> None:
    memory_catalog_dir = _test_dir(artifact_tmp_path, "three-channels-memory")
    embedding_catalog_dir = _test_dir(artifact_tmp_path, "three-channels-embedding")
    cases = [
        _memory_case(
            case_id="memory:a",
            input_summary="device recovery priority path",
            tags=["priority", "device"],
        ),
        _memory_case(
            case_id="memory:b",
            input_summary="generic fallback path",
            tags=["priority"],
        ),
    ]
    _save_cases(memory_catalog_dir, cases)
    _save_embedding_assets(embedding_catalog_dir, cases)

    result = MemoryRetrievalEvaluationService().evaluate_case(
        str(memory_catalog_dir),
        _evaluation_case(
            query=RecoveryCaseQuery(action_name="create_run", tags=["priority", "device"]),
            vector_query_text="device recovery priority",
            expected_case_ids=["memory:a"],
        ),
        embedding_catalog_dir=str(embedding_catalog_dir),
    )

    assert result.evaluated_cases == 1
    assert len(result.results) == 3
    assert {channel.channel.value for channel in result.results} == {
        "deterministic",
        "vector",
        "hybrid",
    }
    assert all(channel.decision == MemoryRetrievalEvaluationDecision.PASSED for channel in result.results)


def test_deterministic_channel_passes_when_expected_case_is_hit(artifact_tmp_path) -> None:
    memory_catalog_dir = _test_dir(artifact_tmp_path, "deterministic-pass")
    case = _memory_case(case_id="memory:a", tags=["priority", "device"])
    _save_cases(memory_catalog_dir, [case])

    result = MemoryRetrievalEvaluationService().evaluate_case(
        str(memory_catalog_dir),
        _evaluation_case(
            query=RecoveryCaseQuery(action_name="create_run", tags=["priority"]),
            expected_case_ids=["memory:a"],
        ),
    )

    deterministic = next(
        channel for channel in result.results if channel.channel.value == "deterministic"
    )
    assert deterministic.decision == MemoryRetrievalEvaluationDecision.PASSED
    assert deterministic.matched_expected_case_ids == ["memory:a"]
    assert deterministic.top_hit is True


def test_vector_channel_hits_from_embedding_catalog_and_points_back_to_memory_case(artifact_tmp_path) -> None:
    memory_catalog_dir = _test_dir(artifact_tmp_path, "vector-memory")
    embedding_catalog_dir = _test_dir(artifact_tmp_path, "vector-embedding")
    cases = [
        _memory_case(
            case_id="memory:a",
            input_summary="device recovery priority path",
            tags=["priority", "device"],
        ),
        _memory_case(
            case_id="memory:b",
            input_summary="generic fallback path",
            tags=["fallback"],
        ),
    ]
    _save_cases(memory_catalog_dir, cases)
    _save_embedding_assets(embedding_catalog_dir, cases)

    result = MemoryRetrievalEvaluationService().evaluate_case(
        str(memory_catalog_dir),
        _evaluation_case(
            query=RecoveryCaseQuery(),
            vector_query_text="device recovery priority",
            expected_case_ids=["memory:a"],
        ),
        embedding_catalog_dir=str(embedding_catalog_dir),
    )

    vector_channel = next(
        channel for channel in result.results if channel.channel.value == "vector"
    )
    assert vector_channel.decision == MemoryRetrievalEvaluationDecision.PASSED
    assert vector_channel.top_case_ids == ["memory:a"]
    assert vector_channel.matched_expected_case_ids == ["memory:a"]


def test_hybrid_channel_preserves_merge_and_hit_behavior(artifact_tmp_path) -> None:
    memory_catalog_dir = _test_dir(artifact_tmp_path, "hybrid-pass-memory")
    embedding_catalog_dir = _test_dir(artifact_tmp_path, "hybrid-pass-embedding")
    cases = [
        _memory_case(
            case_id="memory:a",
            input_summary="device recovery priority path",
            tags=["priority", "device"],
        ),
        _memory_case(
            case_id="memory:b",
            input_summary="priority note",
            tags=["priority"],
        ),
    ]
    _save_cases(memory_catalog_dir, cases)
    _save_embedding_assets(embedding_catalog_dir, cases)

    result = MemoryRetrievalEvaluationService().evaluate_case(
        str(memory_catalog_dir),
        _evaluation_case(
            query=RecoveryCaseQuery(action_name="create_run", tags=["priority"]),
            vector_query_text="device recovery priority",
            expected_case_ids=["memory:a"],
        ),
        embedding_catalog_dir=str(embedding_catalog_dir),
    )

    hybrid_channel = next(
        channel for channel in result.results if channel.channel.value == "hybrid"
    )
    assert hybrid_channel.decision == MemoryRetrievalEvaluationDecision.PASSED
    assert hybrid_channel.top_case_ids[0] == "memory:a"
    assert hybrid_channel.top_hit is True


def test_channel_fails_when_results_do_not_hit_expected_case_ids(artifact_tmp_path) -> None:
    memory_catalog_dir = _test_dir(artifact_tmp_path, "unexpected-hit")
    cases = [
        _memory_case(case_id="memory:a", tags=["priority"]),
        _memory_case(case_id="memory:b", tags=["priority", "device"]),
    ]
    _save_cases(memory_catalog_dir, cases)

    result = MemoryRetrievalEvaluationService().evaluate_case(
        str(memory_catalog_dir),
        _evaluation_case(
            query=RecoveryCaseQuery(action_name="create_run", tags=["priority"]),
            expected_case_ids=["memory:z"],
        ),
    )

    deterministic = next(
        channel for channel in result.results if channel.channel.value == "deterministic"
    )
    assert deterministic.decision == MemoryRetrievalEvaluationDecision.FAILED
    assert deterministic.matched_expected_case_ids == []
    assert deterministic.unexpected_case_ids == ["memory:a", "memory:b"]


def test_channel_without_matches_fails_with_no_retrieval_evidence_summary(artifact_tmp_path) -> None:
    memory_catalog_dir = _test_dir(artifact_tmp_path, "no-matches")
    case = _memory_case(case_id="memory:a", tags=["priority"])
    _save_cases(memory_catalog_dir, [case])

    result = MemoryRetrievalEvaluationService().evaluate_case(
        str(memory_catalog_dir),
        _evaluation_case(
            query=RecoveryCaseQuery(action_name="cancel_run"),
            vector_query_text="unmatched terms",
            expected_case_ids=["memory:a"],
        ),
    )

    deterministic = next(
        channel for channel in result.results if channel.channel.value == "deterministic"
    )
    vector = next(channel for channel in result.results if channel.channel.value == "vector")

    assert deterministic.decision == MemoryRetrievalEvaluationDecision.FAILED
    assert vector.decision == MemoryRetrievalEvaluationDecision.FAILED
    assert "no retrieval evidence" in deterministic.summary
    assert "no retrieval evidence" in vector.summary


def test_empty_vector_index_fails_vector_and_preserves_hybrid_fallback(artifact_tmp_path) -> None:
    memory_catalog_dir = _test_dir(artifact_tmp_path, "vector-fallback-memory")
    empty_embedding_catalog_dir = _test_dir(artifact_tmp_path, "vector-fallback-embedding")
    case = _memory_case(case_id="memory:a", tags=["priority", "device"])
    _save_cases(memory_catalog_dir, [case])

    result = MemoryRetrievalEvaluationService().evaluate_case(
        str(memory_catalog_dir),
        _evaluation_case(
            query=RecoveryCaseQuery(action_name="create_run", tags=["priority"]),
            vector_query_text="device priority",
            expected_case_ids=["memory:a"],
        ),
        embedding_catalog_dir=str(empty_embedding_catalog_dir),
    )

    vector_channel = next(
        channel for channel in result.results if channel.channel.value == "vector"
    )
    hybrid_channel = next(
        channel for channel in result.results if channel.channel.value == "hybrid"
    )

    assert vector_channel.decision == MemoryRetrievalEvaluationDecision.FAILED
    assert hybrid_channel.decision == MemoryRetrievalEvaluationDecision.PASSED
    assert "no indexed vector records" in result.summary


def test_evaluate_cases_aggregates_channel_counts(artifact_tmp_path) -> None:
    memory_catalog_dir = _test_dir(artifact_tmp_path, "aggregate-memory")
    embedding_catalog_dir = _test_dir(artifact_tmp_path, "aggregate-embedding")
    cases = [
        _memory_case(
            case_id="memory:a",
            input_summary="device recovery priority path",
            tags=["priority", "device"],
        ),
        _memory_case(case_id="memory:b", input_summary="generic path", tags=["priority"]),
    ]
    _save_cases(memory_catalog_dir, cases)
    _save_embedding_assets(embedding_catalog_dir, cases)

    result = MemoryRetrievalEvaluationService().evaluate_cases(
        str(memory_catalog_dir),
        [
            _evaluation_case(
                evaluation_case_id="eval-case:passed",
                query=RecoveryCaseQuery(action_name="create_run", tags=["priority"]),
                vector_query_text="device recovery priority",
                expected_case_ids=["memory:a"],
            ),
            _evaluation_case(
                evaluation_case_id="eval-case:failed",
                query=RecoveryCaseQuery(action_name="create_run", tags=["priority"]),
                vector_query_text="device recovery priority",
                expected_case_ids=["memory:z"],
            ),
        ],
        embedding_catalog_dir=str(embedding_catalog_dir),
    )

    assert result.evaluated_cases == 2
    assert result.passed_channels == 3
    assert result.warning_channels == 0
    assert result.failed_channels == 3


def test_save_load_and_catalog_roundtrip_are_stable(artifact_tmp_path) -> None:
    memory_catalog_dir = _test_dir(artifact_tmp_path, "persist-memory")
    embedding_catalog_dir = _test_dir(artifact_tmp_path, "persist-embedding")
    output_dir = _test_dir(artifact_tmp_path, "persist-output")
    result_catalog_dir = _test_dir(artifact_tmp_path, "persist-catalog")
    case = _memory_case(case_id="memory:a", tags=["priority", "device"])
    _save_cases(memory_catalog_dir, [case])
    _save_embedding_assets(embedding_catalog_dir, [case])
    service = MemoryRetrievalEvaluationService()
    result = service.evaluate_case(
        str(memory_catalog_dir),
        _evaluation_case(
            query=RecoveryCaseQuery(action_name="create_run", tags=["priority"]),
            vector_query_text="device priority",
            expected_case_ids=["memory:a"],
        ),
        embedding_catalog_dir=str(embedding_catalog_dir),
    )

    entry = service.save_result(result, str(output_dir / "evaluation.json"))
    restored = service.load_result(str(output_dir / "evaluation.json"))
    service.save_to_catalog(result, str(result_catalog_dir))
    service.save_to_catalog(
        result.model_copy(update={"evaluation_id": "memory-retrieval-evaluation:aaa"}),
        str(result_catalog_dir),
    )
    catalog = service.list_catalog(str(result_catalog_dir))

    assert entry.evaluation_id == result.evaluation_id
    assert restored.evaluation_id == result.evaluation_id
    assert isinstance(catalog, MemoryRetrievalEvaluationCatalog)
    assert [item.evaluation_id for item in catalog.entries] == sorted(
        [result.evaluation_id, "memory-retrieval-evaluation:aaa"]
    )


def test_assets_and_document_support_roundtrip() -> None:
    evaluation_case = _evaluation_case(
        query=RecoveryCaseQuery(action_name="create_run", tags=["priority"]),
        vector_query_text="device priority",
        filters=MemoryCatalogFilter(tags_all=["priority"]),
        expected_case_ids=["memory:a"],
    )
    channel_result = MemoryRetrievalEvaluationChannelResult(
        evaluation_case_id="eval-case:1",
        channel=MemoryRetrievalEvaluationChannel.DETERMINISTIC,
        decision=MemoryRetrievalEvaluationDecision.PASSED,
        matched_expected_case_ids=["memory:a"],
        missed_expected_case_ids=[],
        unexpected_case_ids=[],
        top_case_ids=["memory:a"],
        match_count=1,
        hit_count=1,
        top_hit=True,
        summary="roundtrip channel",
    )
    result = MemoryRetrievalEvaluationResult(
        evaluation_id="memory-retrieval-evaluation:roundtrip",
        catalog_dir="memory-catalog",
        embedding_catalog_dir="embedding-catalog",
        evaluated_cases=1,
        passed_channels=1,
        warning_channels=0,
        failed_channels=0,
        results=[channel_result],
        summary="roundtrip summary",
    )
    document = MemoryRetrievalEvaluationDocument(evaluation=result)

    restored_case = MemoryRetrievalEvaluationCase.model_validate(
        evaluation_case.model_dump(mode="json")
    )
    restored_result = MemoryRetrievalEvaluationResult.model_validate(
        result.model_dump(mode="json")
    )
    restored_document = MemoryRetrievalEvaluationDocument.model_validate(
        document.model_dump(mode="json")
    )

    assert restored_case.schema_version == MemoryRetrievalEvaluationSchemaVersion.V1
    assert restored_result.schema_version == MemoryRetrievalEvaluationSchemaVersion.V1
    assert restored_document.evaluation.evaluation_id == result.evaluation_id


def test_empty_memory_catalog_returns_failed_summary_instead_of_exception(artifact_tmp_path) -> None:
    memory_catalog_dir = _test_dir(artifact_tmp_path, "empty-memory")

    result = MemoryRetrievalEvaluationService().evaluate_case(
        str(memory_catalog_dir),
        _evaluation_case(
            query=RecoveryCaseQuery(action_name="create_run"),
            vector_query_text="device priority",
            expected_case_ids=["memory:a"],
        ),
    )

    assert result.failed_channels == 3
    assert "no candidate evidence" in result.results[0].summary


def test_missing_memory_catalog_directory_raises_file_not_found(artifact_tmp_path) -> None:
    missing_dir = _test_dir(artifact_tmp_path, "missing").parent / f"missing-{uuid4().hex}"

    with pytest.raises(FileNotFoundError, match="Memory case catalog directory does not exist"):
        MemoryRetrievalEvaluationService().evaluate_case(
            str(missing_dir),
            _evaluation_case(
                query=RecoveryCaseQuery(action_name="create_run"),
                expected_case_ids=["memory:a"],
            ),
        )


def test_invalid_memory_and_embedding_documents_keep_existing_error_boundaries(artifact_tmp_path) -> None:
    invalid_memory_dir = _test_dir(artifact_tmp_path, "invalid-memory")
    invalid_embedding_dir = _test_dir(artifact_tmp_path, "invalid-embedding")
    (invalid_memory_dir / "broken.json").write_text(
        json.dumps({"schema_version": "v1", "case": {"oops": True}}),
        encoding="utf-8",
    )
    (invalid_embedding_dir / "broken.json").write_text("{not-json", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid memory case document schema"):
        MemoryRetrievalEvaluationService().evaluate_case(
            str(invalid_memory_dir),
            _evaluation_case(
                query=RecoveryCaseQuery(action_name="create_run"),
                expected_case_ids=["memory:a"],
            ),
        )

    valid_memory_dir = _test_dir(artifact_tmp_path, "valid-memory")
    _save_cases(valid_memory_dir, [_memory_case(case_id="memory:a", tags=["priority"])])
    with pytest.raises(ValueError, match="Invalid memory embedding JSON document"):
        MemoryRetrievalEvaluationService().evaluate_case(
            str(valid_memory_dir),
            _evaluation_case(
                query=RecoveryCaseQuery(action_name="create_run"),
                vector_query_text="priority",
                expected_case_ids=["memory:a"],
            ),
            embedding_catalog_dir=str(invalid_embedding_dir),
        )


def test_empty_expected_case_ids_raise_value_error(artifact_tmp_path) -> None:
    memory_catalog_dir = _test_dir(artifact_tmp_path, "empty-expected")
    _save_cases(memory_catalog_dir, [_memory_case(case_id="memory:a", tags=["priority"])])

    with pytest.raises(ValueError, match="requires at least one expected_case_id"):
        MemoryRetrievalEvaluationService().evaluate_case(
            str(memory_catalog_dir),
            _evaluation_case(
                query=RecoveryCaseQuery(action_name="create_run"),
                expected_case_ids=[],
            ),
        )


def test_invalid_evaluation_document_raises_value_error(artifact_tmp_path) -> None:
    path = _test_dir(artifact_tmp_path, "invalid-evaluation-document") / "broken.json"
    path.write_text(
        json.dumps({"schema_version": "v1", "evaluation": {"oops": True}}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Invalid memory retrieval evaluation document schema"):
        MemoryRetrievalEvaluationService().load_result(str(path))


