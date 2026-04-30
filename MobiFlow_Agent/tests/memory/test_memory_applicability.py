from mobiflow_agent.common.contracts import EntityKind
from mobiflow_agent.memory import InMemoryTaskMemoryStore, TaskMemoryRecord, TaskMemoryRecordKind, TaskMemoryQuery
from mobiflow_agent.memory.retrieval import TaskMemoryRetrievalService
from mobiflow_agent.memory.store import build_memory_timestamp_ms
from mobiflow_agent.task.plan import TaskStepKind


def _record(memory_id: str, *, screen_id: str, failure_type: str, summary: str) -> TaskMemoryRecord:
    now_ms = build_memory_timestamp_ms()
    return TaskMemoryRecord(
        memory_id=memory_id,
        kind=TaskMemoryRecordKind.RECOVERY_PATTERN,
        source="test",
        goal="Recover login flow",
        target_kind=EntityKind.TASK,
        target_id="login",
        step_kind=TaskStepKind.RECOVER,
        role_scope="recovery",
        blocked_reason=failure_type,
        summary=summary,
        tags=["recovery"],
        evidence_ref_ids=["evidence-1"],
        content_payload={
            "applicability": {
                "screen_id": screen_id,
                "failure_type": failure_type,
                "recovery_action": "retry_current_step",
            }
        },
        created_at_ms=now_ms,
        updated_at_ms=now_ms,
    )


def test_memory_retrieval_boosts_matching_applicability_context() -> None:
    store = InMemoryTaskMemoryStore()
    store.put_record(_record("memory:matching", screen_id="loading", failure_type="slow_loading", summary="Retry loading."))
    store.put_record(_record("memory:other", screen_id="login", failure_type="missing_password", summary="Fill password."))
    service = TaskMemoryRetrievalService(store=store)

    result = service.deterministic_retrieve(
        TaskMemoryQuery(
            kinds=[TaskMemoryRecordKind.RECOVERY_PATTERN],
            goal_text="Recover login flow",
            target_kind=EntityKind.TASK,
            target_id="login",
            top_k=2,
            min_score=0,
            applicability_context={
                "screen_id": "loading",
                "failure_type": "slow_loading",
                "recovery_action": "retry_current_step",
            },
        )
    )

    assert result.matches[0].record.memory_id == "memory:matching"
    assert "applicability:screen_id" in result.matches[0].matched_terms
    assert result.matches[0].score > result.matches[1].score
