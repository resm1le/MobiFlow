from __future__ import annotations

from mobiflow_agent.common.contracts import EntityKind, EvidenceKind, EvidenceRef, VerificationStatus, VerificationVerdict
from mobiflow_agent.execution.recovery.execution import GovernedRecoveryExecutionResponse
from mobiflow_agent.memory.case import (
    MemoryCaseSchemaVersion,
    RecoveryCaseQuery,
    RecoveryMemoryCase,
)
from mobiflow_agent.memory.case import MemoryCaseRetrievalService
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


def _memory_case(
    *,
    case_id: str,
    category: str,
    action_name: str,
    decision: RecoveryFollowupDriverDecision,
    verdict_status: VerificationStatus | None,
    tags: list[str] | None = None,
) -> RecoveryMemoryCase:
    service = MemoryCaseRetrievalService()
    replay_case = _replay_case(
        case_id=f"replay:{case_id}",
        action_name=action_name,
        decision=decision,
        verdict_status=verdict_status,
    )
    return service.build_case(
        source="catalog",
        replay_case=replay_case,
        category=category,
        input_summary=f"{case_id} summary",
        tags=tags,
    ).model_copy(update={"case_id": case_id})


def test_build_case_extracts_action_decision_and_verdict_status() -> None:
    service = MemoryCaseRetrievalService()
    replay_case = _replay_case(
        action_name="create_single_device_run",
        decision=RecoveryFollowupDriverDecision.HANDOFF_ONLY,
        verdict_status=VerificationStatus.BLOCKED,
    )

    memory_case = service.build_case(
        source="manual",
        replay_case=replay_case,
        category="device-recovery",
        input_summary="single device recovery case",
        tags=["device", "blocked"],
    )

    assert memory_case.schema_version == MemoryCaseSchemaVersion.V1
    assert memory_case.case_id.startswith("memory:")
    assert memory_case.action_name == "create_single_device_run"
    assert memory_case.decision == RecoveryFollowupDriverDecision.HANDOFF_ONLY
    assert memory_case.verdict_status == VerificationStatus.BLOCKED


def test_build_case_without_eval_case_is_valid() -> None:
    service = MemoryCaseRetrievalService()
    replay_case = _replay_case()

    memory_case = service.build_case(
        source="manual",
        replay_case=replay_case,
        category="followup",
        input_summary="no eval case",
    )

    assert memory_case.eval_case is None
    assert memory_case.replay_case is replay_case


def test_recovery_memory_case_supports_roundtrip() -> None:
    memory_case = _memory_case(
        case_id="memory:test",
        category="followup",
        action_name="create_run",
        decision=RecoveryFollowupDriverDecision.COMPLETE,
        verdict_status=VerificationStatus.VERIFIED_SUCCESS,
        tags=["tag-a", "tag-b"],
    )

    restored = RecoveryMemoryCase.model_validate(memory_case.model_dump(mode="python"))

    assert restored.schema_version == MemoryCaseSchemaVersion.V1
    assert restored.case_id == "memory:test"
    assert restored.tags == ["tag-a", "tag-b"]


def test_recovery_case_query_supports_roundtrip() -> None:
    query = RecoveryCaseQuery(
        category="followup",
        action_name="create_run",
        decision=RecoveryFollowupDriverDecision.COMPLETE,
        verdict_status=VerificationStatus.VERIFIED_SUCCESS,
        tags=["stable", "queued"],
        limit=3,
    )

    restored = RecoveryCaseQuery.model_validate(query.model_dump(mode="python"))

    assert restored.schema_version == MemoryCaseSchemaVersion.V1
    assert restored.action_name == "create_run"
    assert restored.limit == 3


def test_retrieve_prioritizes_action_name_match() -> None:
    service = MemoryCaseRetrievalService()
    exact = _memory_case(
        case_id="memory:a",
        category="alpha",
        action_name="create_run",
        decision=RecoveryFollowupDriverDecision.COMPLETE,
        verdict_status=VerificationStatus.VERIFIED_SUCCESS,
    )
    category_only = _memory_case(
        case_id="memory:b",
        category="followup",
        action_name="cancel_run",
        decision=RecoveryFollowupDriverDecision.COMPLETE,
        verdict_status=VerificationStatus.VERIFIED_SUCCESS,
    )

    response = service.retrieve(
        query=RecoveryCaseQuery(action_name="create_run", category="followup"),
        cases=[category_only, exact],
    )

    assert [match.case.case_id for match in response.matches] == ["memory:a", "memory:b"]


def test_retrieve_orders_by_total_score_across_multiple_fields() -> None:
    service = MemoryCaseRetrievalService()
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

    response = service.retrieve(
        query=RecoveryCaseQuery(
            category="followup",
            action_name="create_run",
            decision=RecoveryFollowupDriverDecision.COMPLETE,
            verdict_status=VerificationStatus.VERIFIED_SUCCESS,
            tags=["priority", "device"],
        ),
        cases=[weaker, strongest],
    )

    assert [match.case.case_id for match in response.matches] == ["memory:a", "memory:b"]
    assert response.matches[0].score > response.matches[1].score


def test_retrieve_uses_case_id_for_stable_tiebreak() -> None:
    service = MemoryCaseRetrievalService()
    case_b = _memory_case(
        case_id="memory:b",
        category="followup",
        action_name="create_run",
        decision=RecoveryFollowupDriverDecision.COMPLETE,
        verdict_status=VerificationStatus.VERIFIED_SUCCESS,
    )
    case_a = _memory_case(
        case_id="memory:a",
        category="followup",
        action_name="create_run",
        decision=RecoveryFollowupDriverDecision.COMPLETE,
        verdict_status=VerificationStatus.VERIFIED_SUCCESS,
    )

    response = service.retrieve(
        query=RecoveryCaseQuery(action_name="create_run"),
        cases=[case_b, case_a],
    )

    assert [match.case.case_id for match in response.matches] == ["memory:a", "memory:b"]


def test_retrieve_respects_limit() -> None:
    service = MemoryCaseRetrievalService()
    cases = [
        _memory_case(
            case_id=f"memory:{index}",
            category="followup",
            action_name="create_run",
            decision=RecoveryFollowupDriverDecision.COMPLETE,
            verdict_status=VerificationStatus.VERIFIED_SUCCESS,
        )
        for index in range(3)
    ]

    response = service.retrieve(
        query=RecoveryCaseQuery(action_name="create_run", limit=2),
        cases=cases,
    )

    assert len(response.matches) == 2


def test_retrieve_with_empty_query_returns_no_matches() -> None:
    service = MemoryCaseRetrievalService()
    cases = [
        _memory_case(
            case_id="memory:a",
            category="followup",
            action_name="create_run",
            decision=RecoveryFollowupDriverDecision.COMPLETE,
            verdict_status=VerificationStatus.VERIFIED_SUCCESS,
        )
    ]

    response = service.retrieve(
        query=RecoveryCaseQuery(),
        cases=cases,
    )

    assert response.matches == []
    assert "requires at least one query filter" in response.summary


def test_memory_case_retrieval_service_is_pure_and_does_not_execute_flows() -> None:
    service = MemoryCaseRetrievalService()
    replay_case = _replay_case()
    eval_case = RecoveryEvalCase(
        case_id="eval:test",
        category="followup",
        input_summary="test eval case",
        expected_decision=RecoveryFollowupDriverDecision.COMPLETE,
        expected_verdict_status=VerificationStatus.VERIFIED_SUCCESS,
        replay_case=replay_case,
    )

    memory_case = service.build_case(
        source="manual",
        replay_case=replay_case,
        eval_case=eval_case,
        category="followup",
        input_summary="pure service",
        tags=["stable"],
    )
    response = service.retrieve(
        query=RecoveryCaseQuery(action_name="create_run", tags=["stable"]),
        cases=[memory_case],
    )

    assert memory_case.replay_case is replay_case
    assert memory_case.eval_case is eval_case
    assert response.matches[0].case is memory_case

