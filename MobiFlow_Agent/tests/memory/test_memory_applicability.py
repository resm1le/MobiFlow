from mobiflow_agent.agents import AgentRole
from mobiflow_agent.common.contracts import EntityKind, VerificationStatus, VerificationVerdict
from mobiflow_agent.memory import (
    InMemoryTaskMemoryStore,
    TaskMemoryPolicy,
    TaskMemoryRecord,
    TaskMemoryRecordKind,
    TaskMemoryQuery,
    TaskMemoryRecordStatus,
)
from mobiflow_agent.memory.retrieval import TaskMemoryRetrievalService
from mobiflow_agent.memory.runtime import TaskMemoryRuntime
from mobiflow_agent.memory.store import build_memory_timestamp_ms
from mobiflow_agent.task.plan import TaskPlan, TaskStep, TaskStepKind
from mobiflow_agent.task.session import TaskSession


def _record(
    memory_id: str,
    *,
    screen_id: str,
    failure_type: str,
    summary: str,
    confidence_score: float = 0.5,
    feedback: dict | None = None,
) -> TaskMemoryRecord:
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
        confidence_score=confidence_score,
        feedback=feedback or {},
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


def test_memory_retrieval_penalizes_negative_feedback() -> None:
    store = InMemoryTaskMemoryStore()
    store.put_record(
        _record(
            "memory:risky",
            screen_id="loading",
            failure_type="slow_loading",
            summary="Risky retry.",
            confidence_score=0.9,
            feedback={"failure_count": 3},
        )
    )
    store.put_record(
        _record(
            "memory:trusted",
            screen_id="loading",
            failure_type="slow_loading",
            summary="Trusted retry.",
            confidence_score=0.8,
            feedback={"success_count": 2},
        )
    )

    result = TaskMemoryRetrievalService(store=store).deterministic_retrieve(
        TaskMemoryQuery(
            kinds=[TaskMemoryRecordKind.RECOVERY_PATTERN],
            goal_text="Recover login flow",
            target_kind=EntityKind.TASK,
            target_id="login",
            top_k=2,
            min_score=0,
            applicability_context={"screen_id": "loading", "failure_type": "slow_loading"},
        )
    )

    assert result.matches[0].record.memory_id == "memory:trusted"
    assert result.matches[0].score > result.matches[1].score
    assert "risk=negative_feedback_threshold" in result.matches[1].summary


def test_memory_runtime_records_negative_feedback_for_retrieved_memory() -> None:
    store = InMemoryTaskMemoryStore()
    store.put_record(
        _record(
            "memory:used",
            screen_id="loading",
            failure_type="slow_loading",
            summary="Use retry.",
            confidence_score=0.7,
        )
    )
    runtime = TaskMemoryRuntime(store=store)
    step = TaskStep(step_id="recover-step", kind=TaskStepKind.RECOVER, goal="Recover login flow.")
    session = TaskSession(
        session_id="session-negative-feedback",
        goal="Recover login flow",
        target_kind=EntityKind.TASK,
        target_id="login",
        plan=TaskPlan(plan_id="plan-1", summary="Recover.", steps=[step]),
        current_step=step,
    )
    runtime.prepare_context(session, role=AgentRole.RECOVERY)
    session.last_verdict = VerificationVerdict(
        verdict_id="verdict-unknown",
        status=VerificationStatus.VERIFIED_UNKNOWN,
        summary="Recovery did not work.",
        target_kind=EntityKind.TASK,
        target_id="login",
        unmatched_check_ids=["home"],
    )

    runtime.writeback_session(session)

    updated = store.get_record("memory:used")
    assert updated is not None
    assert updated.feedback["failure_count"] == 1
    assert updated.confidence_score < 0.7


def test_memory_runtime_marks_risky_and_quarantines_repeated_negative_feedback() -> None:
    store = InMemoryTaskMemoryStore()
    store.put_record(
        _record(
            "memory:risky-used",
            screen_id="loading",
            failure_type="slow_loading",
            summary="Repeatedly risky recovery.",
            confidence_score=0.7,
        )
    )
    runtime = TaskMemoryRuntime(
        store=store,
        policy=TaskMemoryPolicy(
            risky_feedback_failure_threshold=1,
            quarantine_feedback_failure_threshold=2,
        ),
    )
    step = TaskStep(step_id="recover-step", kind=TaskStepKind.RECOVER, goal="Recover login flow.")
    session = TaskSession(
        session_id="session-risky-feedback",
        goal="Recover login flow",
        target_kind=EntityKind.TASK,
        target_id="login",
        plan=TaskPlan(plan_id="plan-1", summary="Recover.", steps=[step]),
        current_step=step,
    )
    runtime.prepare_context(session, role=AgentRole.RECOVERY)
    session.last_verdict = VerificationVerdict(
        verdict_id="verdict-unknown",
        status=VerificationStatus.VERIFIED_UNKNOWN,
        summary="Recovery did not work.",
        target_kind=EntityKind.TASK,
        target_id="login",
        unmatched_check_ids=["home"],
    )

    runtime.writeback_session(session)
    first = store.get_record("memory:risky-used")
    assert first is not None
    assert "risky_feedback" in first.governance_tags
    assert first.feedback["risk_reason"] == "negative_feedback_threshold"

    runtime.writeback_session(session)
    second = store.get_record("memory:risky-used")
    assert second is not None
    assert second.status == TaskMemoryRecordStatus.QUARANTINED
    assert "quarantined_feedback" in second.governance_tags
