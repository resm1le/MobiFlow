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
    MemoryCatalogRetrievalSchemaVersion,
)
from mobiflow_agent.memory.catalog import MemoryCatalogRetrievalService
from mobiflow_agent.execution.followup.decisions import RecoveryFollowupDriverDecision
from tests.harness_helpers import build_task_harness_response
from mobiflow_agent.evaluation.replay import RecoveryReplayCase
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


def _memory_case(
    *,
    case_id: str,
    source: str = "catalog",
    category: str = "followup",
    action_name: str = "create_run",
    decision: RecoveryFollowupDriverDecision = RecoveryFollowupDriverDecision.COMPLETE,
    verdict_status: VerificationStatus | None = VerificationStatus.VERIFIED_SUCCESS,
    tags: list[str] | None = None,
) -> RecoveryMemoryCase:
    replay_case = _replay_case(
        case_id=f"replay:{case_id}",
        action_name=action_name,
        decision=decision,
        verdict_status=verdict_status,
    )
    return MemoryCaseRetrievalService().build_case(
        source=source,
        replay_case=replay_case,
        category=category,
        input_summary=f"{case_id} summary",
        tags=tags,
    ).model_copy(update={"case_id": case_id})


def _test_dir(artifact_tmp_path: Path, name: str) -> Path:
    return artifact_dir(artifact_tmp_path, name)


def _save_cases(catalog_dir: Path, cases: list[RecoveryMemoryCase]) -> None:
    persistence = MemoryCasePersistenceService()
    for case in cases:
        persistence.save_to_catalog(case=case, catalog_dir=str(catalog_dir))


def test_preview_candidates_filters_by_each_catalog_field(artifact_tmp_path) -> None:
    catalog_dir = _test_dir(artifact_tmp_path, "preview")
    matching = _memory_case(
        case_id="memory:a",
        source="manual",
        category="device-recovery",
        action_name="create_single_device_run",
        decision=RecoveryFollowupDriverDecision.HANDOFF_ONLY,
        verdict_status=VerificationStatus.BLOCKED,
        tags=["device", "priority", "blocked"],
    )
    wrong_tag = _memory_case(
        case_id="memory:b",
        source="manual",
        category="device-recovery",
        action_name="create_single_device_run",
        decision=RecoveryFollowupDriverDecision.HANDOFF_ONLY,
        verdict_status=VerificationStatus.BLOCKED,
        tags=["device"],
    )
    wrong_source = _memory_case(
        case_id="memory:c",
        source="imported",
        category="device-recovery",
        action_name="create_single_device_run",
        decision=RecoveryFollowupDriverDecision.HANDOFF_ONLY,
        verdict_status=VerificationStatus.BLOCKED,
        tags=["device", "priority", "blocked"],
    )
    _save_cases(catalog_dir, [wrong_tag, wrong_source, matching])

    result = MemoryCatalogRetrievalService().preview_candidates(
        str(catalog_dir),
        filters=MemoryCatalogFilter(
            case_ids=["memory:a", "memory:b", "memory:c"],
            sources=["manual"],
            categories=["device-recovery"],
            action_names=["create_single_device_run"],
            decisions=[RecoveryFollowupDriverDecision.HANDOFF_ONLY],
            verdict_statuses=[VerificationStatus.BLOCKED],
            tags_any=["priority"],
            tags_all=["device", "blocked"],
        ),
    )

    assert result.catalog_case_count == 3
    assert result.filtered_case_count == 1
    assert result.matches == []
    assert "1 candidates remain" in result.summary


def test_retrieve_filters_candidates_then_reuses_deterministic_scoring(artifact_tmp_path) -> None:
    catalog_dir = _test_dir(artifact_tmp_path, "retrieve")
    strongest = _memory_case(
        case_id="memory:a",
        category="followup",
        action_name="create_run",
        decision=RecoveryFollowupDriverDecision.COMPLETE,
        verdict_status=VerificationStatus.VERIFIED_SUCCESS,
        tags=["priority", "device"],
    )
    weaker = _memory_case(
        case_id="memory:b",
        category="followup",
        action_name="create_run",
        decision=RecoveryFollowupDriverDecision.COMPLETE,
        verdict_status=VerificationStatus.VERIFIED_FAILED,
        tags=["priority"],
    )
    excluded = _memory_case(
        case_id="memory:c",
        category="followup",
        action_name="create_run",
        decision=RecoveryFollowupDriverDecision.COMPLETE,
        verdict_status=VerificationStatus.VERIFIED_SUCCESS,
        tags=["priority", "skip"],
    )
    _save_cases(catalog_dir, [excluded, weaker, strongest])

    request = MemoryCatalogRetrievalRequest(
        query=RecoveryCaseQuery(
            category="followup",
            action_name="create_run",
            verdict_status=VerificationStatus.VERIFIED_SUCCESS,
            tags=["priority", "device"],
            limit=3,
        ),
        filters=MemoryCatalogFilter(tags_all=["priority"], tags_any=["device"]),
    )
    result = MemoryCatalogRetrievalService().retrieve(str(catalog_dir), request)
    expected = MemoryCaseRetrievalService().retrieve(
        query=request.query,
        cases=[strongest],
    )

    assert result.catalog_case_count == 3
    assert result.filtered_case_count == 1
    assert [match.case.case_id for match in result.matches] == [
        match.case.case_id for match in expected.matches
    ]
    assert result.matches[0].score == expected.matches[0].score


def test_filters_do_not_contribute_to_score(artifact_tmp_path) -> None:
    catalog_dir = _test_dir(artifact_tmp_path, "filter-score")
    case = _memory_case(
        case_id="memory:a",
        category="followup",
        action_name="create_run",
        tags=["priority", "device"],
    )
    _save_cases(catalog_dir, [case])

    result = MemoryCatalogRetrievalService().retrieve(
        str(catalog_dir),
        MemoryCatalogRetrievalRequest(
            query=RecoveryCaseQuery(action_name="create_run"),
            filters=MemoryCatalogFilter(tags_all=["priority", "device"]),
        ),
    )

    assert result.filtered_case_count == 1
    assert result.matches[0].score == 4
    assert result.matches[0].summary == "Matched on action_name=create_run (score=4)."


def test_empty_query_with_filters_returns_no_matches(artifact_tmp_path) -> None:
    catalog_dir = _test_dir(artifact_tmp_path, "empty-query")
    _save_cases(catalog_dir, [_memory_case(case_id="memory:a", tags=["priority"])])

    result = MemoryCatalogRetrievalService().retrieve(
        str(catalog_dir),
        MemoryCatalogRetrievalRequest(
            query=RecoveryCaseQuery(),
            filters=MemoryCatalogFilter(tags_all=["priority"]),
        ),
    )

    assert result.filtered_case_count == 1
    assert result.matches == []
    assert "requires at least one query filter" in result.summary


def test_empty_catalog_returns_no_candidate_evidence_summary(artifact_tmp_path) -> None:
    catalog_dir = _test_dir(artifact_tmp_path, "empty")
    service = MemoryCatalogRetrievalService()

    preview = service.preview_candidates(str(catalog_dir))
    result = service.retrieve(
        str(catalog_dir),
        MemoryCatalogRetrievalRequest(query=RecoveryCaseQuery(action_name="create_run")),
    )

    assert preview.catalog_case_count == 0
    assert preview.filtered_case_count == 0
    assert "no candidate evidence" in preview.summary
    assert result.catalog_case_count == 0
    assert result.filtered_case_count == 0
    assert result.matches == []
    assert "no candidate evidence" in result.summary


def test_retrieve_without_filters_matches_persistence_retrieve_from_catalog(artifact_tmp_path) -> None:
    catalog_dir = _test_dir(artifact_tmp_path, "no-filters")
    cases = [
        _memory_case(case_id="memory:b", action_name="create_run"),
        _memory_case(case_id="memory:a", action_name="create_run"),
    ]
    _save_cases(catalog_dir, cases)
    query = RecoveryCaseQuery(action_name="create_run", limit=2)

    enhanced = MemoryCatalogRetrievalService().retrieve(
        str(catalog_dir),
        MemoryCatalogRetrievalRequest(query=query),
    )
    baseline = MemoryCasePersistenceService().retrieve_from_catalog(
        catalog_dir=str(catalog_dir),
        query=query,
    )

    assert [match.case.case_id for match in enhanced.matches] == [
        match.case.case_id for match in baseline.matches
    ]
    assert [match.score for match in enhanced.matches] == [match.score for match in baseline.matches]


def test_assets_support_roundtrip() -> None:
    request = MemoryCatalogRetrievalRequest(
        query=RecoveryCaseQuery(action_name="create_run"),
        filters=MemoryCatalogFilter(
            sources=["manual"],
            decisions=[RecoveryFollowupDriverDecision.COMPLETE],
            verdict_statuses=[VerificationStatus.VERIFIED_SUCCESS],
        ),
    )
    result = MemoryCatalogRetrievalResult(
        catalog_dir="catalog",
        catalog_case_count=3,
        filtered_case_count=1,
        matches=[],
        applied_filters=request.filters,
        summary="roundtrip",
    )

    restored_request = MemoryCatalogRetrievalRequest.model_validate(request.model_dump(mode="python"))
    restored_result = MemoryCatalogRetrievalResult.model_validate(result.model_dump(mode="python"))

    assert restored_request.schema_version == MemoryCatalogRetrievalSchemaVersion.V1
    assert restored_request.filters is not None
    assert restored_request.filters.sources == ["manual"]
    assert restored_result.schema_version == MemoryCatalogRetrievalSchemaVersion.V1
    assert restored_result.filtered_case_count == 1


def test_missing_catalog_directory_raises_file_not_found(artifact_tmp_path) -> None:
    missing_dir = _test_dir(artifact_tmp_path, "missing").parent / f"missing-{uuid4().hex}"

    with pytest.raises(FileNotFoundError, match="Memory case catalog directory does not exist"):
        MemoryCatalogRetrievalService().preview_candidates(str(missing_dir))


def test_invalid_memory_document_errors_are_owned_by_persistence_layer(artifact_tmp_path) -> None:
    catalog_dir = _test_dir(artifact_tmp_path, "invalid")
    (catalog_dir / "broken.json").write_text(
        json.dumps({"schema_version": "v1", "case": {"oops": True}}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Invalid memory case document schema"):
        MemoryCatalogRetrievalService().retrieve(
            str(catalog_dir),
            MemoryCatalogRetrievalRequest(query=RecoveryCaseQuery(action_name="create_run")),
        )


def test_enhanced_retrieval_is_static_and_catalog_bound(artifact_tmp_path) -> None:
    catalog_dir = _test_dir(artifact_tmp_path, "static")
    case = _memory_case(case_id="memory:static", tags=["stable"])
    _save_cases(catalog_dir, [case])

    result = MemoryCatalogRetrievalService().retrieve(
        str(catalog_dir),
        MemoryCatalogRetrievalRequest(
            query=RecoveryCaseQuery(tags=["stable"]),
            filters=MemoryCatalogFilter(case_ids=["memory:static"]),
        ),
    )

    assert result.matches[0].case.case_id == "memory:static"
    assert result.matches[0].case.replay_case == case.replay_case


