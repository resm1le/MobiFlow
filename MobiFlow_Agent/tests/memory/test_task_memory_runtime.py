from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from mobiflow_agent.agents.contracts import AgentRole, RecoveryOutcome
from mobiflow_agent.agents.observer import ObserverAgent
from mobiflow_agent.agents.recovery import RecoveryAgent
from mobiflow_agent.agents.verifier import VerifierAgent
from mobiflow_agent.common.contracts import (
    EntityKind,
    EvidenceKind,
    EvidenceRef,
    ObservationFact,
    ObservationFactSource,
    ObservationView,
    VerificationCheck,
    VerificationSpec,
    VerificationStatus,
    VerificationVerdict,
)
from mobiflow_agent.control import TaskOrchestratorService
from mobiflow_agent.memory import (
    InMemoryTaskMemoryStore,
    SqliteTaskMemoryStore,
    TaskMemoryPolicy,
    TaskMemoryQualityDecision,
    TaskMemoryQualityService,
    TaskMemoryRecord,
    TaskMemoryRecordKind,
    TaskMemoryRecordStatus,
    TaskMemoryRuntime,
)
from mobiflow_agent.memory.evaluation import TaskMemoryEvaluationCase, TaskMemoryEvaluationService
from mobiflow_agent.memory.models import TaskMemoryQuery
from mobiflow_agent.model import EmbeddingProfile, ModelRegistry, ModelRuntime
from mobiflow_agent.model.providers import NoopEmbeddingClient
from mobiflow_agent.task.plan import TaskStepKind, TaskStatus
from tests.artifacts import sqlite_path


def _observation(observation_id: str, *, status: str) -> ObservationView:
    return ObservationView(
        observation_id=observation_id,
        focus_kind=EntityKind.RUN,
        focus_id="run-123",
        facts=[
            ObservationFact(
                fact_id=f"fact:{observation_id}",
                source=ObservationFactSource.PLATFORM,
                title="Run status",
                value={"status": status},
                evidence_refs=[
                    EvidenceRef(
                        evidence_id=f"evidence:{observation_id}",
                        kind=EvidenceKind.PLATFORM_SNAPSHOT,
                        summary=f"Observed run status {status}.",
                        locator="run-123",
                    )
                ],
            )
        ],
    )


def _verification_spec() -> VerificationSpec:
    return VerificationSpec(
        verification_id="verification:run:run-123",
        target_kind=EntityKind.RUN,
        target_id="run-123",
        success_checks=[
            VerificationCheck(
                check_id="run-healthy",
                description="The run is healthy.",
                evidence_hint="healthy",
            )
        ],
        blocked_conditions=["blocked"],
    )


def test_task_memory_runtime_writes_back_records_and_retrieves_planner_context() -> None:
    observations = [_observation("observe-1", status="healthy")]

    orchestrator = TaskOrchestratorService(
        observer_agent=ObserverAgent(observation_provider=lambda _session: observations.pop(0)),
        verifier_agent=VerifierAgent(),
        recovery_agent=RecoveryAgent(),
        memory_runtime=TaskMemoryRuntime(store=InMemoryTaskMemoryStore()),
    )

    completed = orchestrator.run(
        orchestrator.create_session(
            "Inspect blocked task",
            target_kind=EntityKind.RUN,
            target_id="run-123",
            verification_spec=_verification_spec(),
        )
    )

    records = orchestrator._memory_runtime.list_records()  # noqa: SLF001
    assert completed.status == TaskStatus.COMPLETED
    assert {record.kind for record in records} >= {
        TaskMemoryRecordKind.PLANNING_PATTERN,
        TaskMemoryRecordKind.VERIFICATION_PATTERN,
        TaskMemoryRecordKind.TASK_OUTCOME,
    }

    fresh_session = orchestrator.create_session(
        "Inspect blocked task",
        target_kind=EntityKind.RUN,
        target_id="run-123",
        verification_spec=_verification_spec(),
    )
    context = orchestrator._memory_runtime.prepare_context(fresh_session, role=AgentRole.PLANNER)  # noqa: SLF001
    assert context.matches
    assert context.highlights[0]["kind"] in {
        TaskMemoryRecordKind.PLANNING_PATTERN.value,
        TaskMemoryRecordKind.TASK_OUTCOME.value,
    }


def test_task_memory_runtime_builds_embeddings_when_embedding_profile_is_configured() -> None:
    store = InMemoryTaskMemoryStore()
    registry = ModelRegistry(
        embedding_profiles=[
            EmbeddingProfile(
                name="memory-embedding",
                provider="noop",
                model="noop-embedding-model",
            )
        ],
        embedding_clients={"noop": NoopEmbeddingClient()},
    )
    runtime = TaskMemoryRuntime(
        store=store,
        embedding_profile_name="memory-embedding",
    )
    orchestrator = TaskOrchestratorService(
        observer_agent=ObserverAgent(observation_provider=lambda _session: _observation("observe-1", status="healthy")),
        verifier_agent=VerifierAgent(),
        recovery_agent=RecoveryAgent(),
        memory_runtime=runtime,
        model_registry=registry,
    )

    orchestrator.run(
        orchestrator.create_session(
            "Inspect healthy run",
            target_kind=EntityKind.RUN,
            target_id="run-123",
            verification_spec=_verification_spec(),
        )
    )
    embeddings = store.list_embeddings(profile_name="memory-embedding")

    assert embeddings
    assert embeddings[0].vector


def test_recovery_agent_can_reuse_task_memory_guidance_without_model() -> None:
    store = InMemoryTaskMemoryStore()
    store.put_record(
        TaskMemoryRecord(
            memory_id="task-memory:seed",
            kind=TaskMemoryRecordKind.RECOVERY_PATTERN,
            source="seed",
            goal="Recover blocked run",
            target_kind=EntityKind.RUN,
            target_id="run-123",
            step_kind=TaskStepKind.RECOVER,
            role_scope=AgentRole.RECOVERY.value,
            verdict_status=VerificationStatus.BLOCKED,
            blocked_reason="blocked",
            summary="Prior blocked run used cancel_run as the recommended recovery action.",
            tags=["recovery", "blocked", "verifier"],
            evidence_ref_ids=["evidence:seed"],
            proposal_fingerprint="cancel_run",
            content_payload={
                "recovery_guidance": {
                    "entity_kind": "run",
                    "entity_id": "run-123",
                    "allowed_actions": ["cancel_run"],
                    "recommended_action": "cancel_run",
                    "requires_approval": False,
                    "required_inputs": [],
                    "prerequisites": [],
                    "stop_conditions": ["healthy"],
                    "stop_conditions_summary": "Stop when the run becomes healthy.",
                    "why_not_others": "Prior memory shows cancel_run was the only safe fix.",
                    "explanation": "Reuse the known safe recovery action.",
                    "confidence": 0.9,
                }
            },
            created_at_ms=1,
            updated_at_ms=1,
        )
    )
    observations = [_observation("observe-1", status="blocked")]
    runtime = TaskMemoryRuntime(store=store, policy=TaskMemoryPolicy(recovery_top_k=3))
    orchestrator = TaskOrchestratorService(
        observer_agent=ObserverAgent(observation_provider=lambda _session: observations.pop(0)),
        verifier_agent=VerifierAgent(),
        recovery_agent=RecoveryAgent(),
        memory_runtime=runtime,
    )

    failed = orchestrator.run(
        orchestrator.create_session(
            "Recover blocked run",
            target_kind=EntityKind.RUN,
            target_id="run-123",
            verification_spec=_verification_spec(),
        )
    )

    assert failed.status == TaskStatus.FAILED
    assert failed.recovery_outcome is not None
    assert failed.recovery_outcome.guidance is not None
    assert failed.recovery_outcome.guidance.recommended_action == "cancel_run"


def test_sqlite_task_memory_store_roundtrips_records_and_embeddings(artifact_tmp_path: Path) -> None:
    path = sqlite_path(artifact_tmp_path, "task-memory")
    with SqliteTaskMemoryStore(str(path)) as store:
        record = TaskMemoryRecord(
            memory_id="task-memory:1",
            kind=TaskMemoryRecordKind.TASK_OUTCOME,
            source="test",
            goal="Inspect blocked task",
            target_kind=EntityKind.RUN,
            target_id="run-123",
            role_scope=AgentRole.PLANNER.value,
            summary="Stored memory outcome.",
            tags=["planner"],
            evidence_ref_ids=["evidence:1"],
            proposal_fingerprint="proposal",
            content_payload={},
            created_at_ms=1,
            updated_at_ms=1,
        )
        store.put_record(record)
        store.upsert_embedding(
            orchestrator_entry := runtime_entry()
        )
        restored = store.get_record(record.memory_id)
        embeddings = store.list_embeddings(profile_name=orchestrator_entry.profile_name)

    assert restored is not None
    assert restored.memory_id == record.memory_id
    assert embeddings and embeddings[0].memory_id == record.memory_id


def runtime_entry():
    from mobiflow_agent.memory.models import TaskMemoryEmbeddingEntry

    return TaskMemoryEmbeddingEntry(
        memory_id="task-memory:1",
        profile_name="memory-embedding",
        vector=[1.0, 0.0],
        source_text="stored memory outcome",
        updated_at_ms=1,
    )


def test_task_memory_evaluation_service_compares_deterministic_vector_hybrid_and_no_memory() -> None:
    store = InMemoryTaskMemoryStore()
    store.put_record(
        TaskMemoryRecord(
            memory_id="task-memory:match",
            kind=TaskMemoryRecordKind.TASK_OUTCOME,
            source="test",
            goal="Inspect blocked task",
            target_kind=EntityKind.RUN,
            target_id="run-123",
            role_scope=AgentRole.PLANNER.value,
            verdict_status=VerificationStatus.VERIFIED_SUCCESS,
            summary="The healthy run inspection completed successfully.",
            tags=["planner", "verified_success"],
            evidence_ref_ids=["evidence:1"],
            proposal_fingerprint="proposal",
            content_payload={},
            created_at_ms=1,
            updated_at_ms=1,
        )
    )
    runtime = TaskMemoryRuntime(
        store=store,
        model_runtime=ModelRuntime(
            ModelRegistry(
                embedding_profiles=[EmbeddingProfile(name="memory-embedding", provider="noop", model="noop")],
                embedding_clients={"noop": NoopEmbeddingClient()},
            )
        ),
        embedding_profile_name="memory-embedding",
    )
    runtime.ensure_record_embeddings(store.list_records())
    service = TaskMemoryEvaluationService(store=store, memory_runtime=runtime)

    result = service.evaluate_cases(
        [
            TaskMemoryEvaluationCase(
                evaluation_case_id="case-1",
                query=TaskMemoryQuery(
                    role_scope=AgentRole.PLANNER.value,
                    kinds=[TaskMemoryRecordKind.TASK_OUTCOME],
                    goal_text="Inspect blocked task",
                    target_kind=EntityKind.RUN,
                    target_id="run-123",
                    semantic_query_text="healthy run inspection",
                    top_k=3,
                ),
                expected_memory_ids=["task-memory:match"],
                summary="Expect the stored task outcome to be recalled.",
            )
        ]
    )

    assert result.evaluated_cases == 1
    assert {channel.channel.value for channel in result.results} == {"deterministic", "vector", "hybrid", "none"}
    assert any(
        channel.decision.value == "passed"
        for channel in result.results
        if channel.channel.value != "none"
    )
    assert result.hit_rate > 0
    assert result.top_hit_rate > 0


def test_task_memory_quality_gate_rejects_unknown_writeback() -> None:
    store = InMemoryTaskMemoryStore()
    runtime = TaskMemoryRuntime(store=store)
    session = TaskOrchestratorService(memory_runtime=runtime).create_session(
        "Inspect pending run",
        target_kind=EntityKind.RUN,
        target_id="run-123",
        verification_spec=_verification_spec(),
    )
    session.last_verdict = VerificationVerdict(
        verdict_id="verdict:unknown",
        status=VerificationStatus.VERIFIED_UNKNOWN,
        summary="Current evidence is inconclusive.",
        target_kind=EntityKind.RUN,
        target_id="run-123",
        evidence_refs=[
            EvidenceRef(
                evidence_id="evidence:unknown",
                kind=EvidenceKind.PLATFORM_SNAPSHOT,
                summary="Observed pending status.",
                locator="run-123",
            )
        ],
    )

    result = runtime.writeback_session(session)

    assert store.query_records(TaskMemoryQuery(goal_text="Inspect pending run")) == []
    assert store.list_records(statuses=[TaskMemoryRecordStatus.QUARANTINED])
    assert result.quarantined_count > 0
    assert "quarantined" in result.summary


def test_task_memory_writeback_updates_duplicate_fingerprint() -> None:
    store = InMemoryTaskMemoryStore()
    runtime = TaskMemoryRuntime(store=store)

    def run_once(observation_id: str) -> None:
        orchestrator = TaskOrchestratorService(
            observer_agent=ObserverAgent(
                observation_provider=lambda _session: _observation(observation_id, status="healthy")
            ),
            verifier_agent=VerifierAgent(),
            recovery_agent=RecoveryAgent(),
            memory_runtime=runtime,
        )
        orchestrator.run(
            orchestrator.create_session(
                "Inspect healthy run",
                target_kind=EntityKind.RUN,
                target_id="run-123",
                verification_spec=_verification_spec(),
            )
        )

    run_once("observe-1")
    first_result = runtime.writeback_results()[-1]
    run_once("observe-2")
    second_result = runtime.writeback_results()[-1]

    assert first_result.created_count > 0
    assert second_result.updated_count > 0
    assert len(store.list_records()) == first_result.created_count


def test_task_memory_quality_service_rejects_invalid_recovery_guidance() -> None:
    record = TaskMemoryRecord(
        memory_id="task-memory:bad-guidance",
        kind=TaskMemoryRecordKind.RECOVERY_PATTERN,
        source="test",
        goal="Recover blocked run",
        target_kind=EntityKind.RUN,
        target_id="run-123",
        step_kind=TaskStepKind.RECOVER,
        role_scope=AgentRole.RECOVERY.value,
        verdict_status=VerificationStatus.BLOCKED,
        blocked_reason="blocked",
        summary="Blocked recovery with malformed guidance.",
        tags=["recovery"],
        evidence_ref_ids=["evidence:1"],
        proposal_fingerprint="recover",
        content_payload={"recovery_guidance": {"recommended_action": "cancel_run"}},
        created_at_ms=1,
        updated_at_ms=1,
    )

    assessment = TaskMemoryQualityService().assess_record(record)

    assert assessment.decision == TaskMemoryQualityDecision.FAILED
    assert any(issue.code == "invalid_recovery_guidance" for issue in assessment.issues)


def test_task_memory_retrieval_filters_inactive_and_expired_records() -> None:
    store = InMemoryTaskMemoryStore()
    active = _task_memory_record("active", status=TaskMemoryRecordStatus.ACTIVE)
    quarantined = _task_memory_record("quarantined", status=TaskMemoryRecordStatus.QUARANTINED)
    expired = _task_memory_record("expired", status=TaskMemoryRecordStatus.ACTIVE, expires_at_ms=1)
    for record in (active, quarantined, expired):
        store.put_record(record)

    default_matches = store.query_records(
        TaskMemoryQuery(goal_text="Inspect governed memory", semantic_query_text="governed memory")
    )
    quarantined_matches = store.query_records(
        TaskMemoryQuery(
            goal_text="Inspect governed memory",
            semantic_query_text="governed memory",
            statuses=[TaskMemoryRecordStatus.QUARANTINED],
        )
    )

    assert [record.memory_id for record in default_matches] == ["task-memory:active"]
    assert [record.memory_id for record in quarantined_matches] == ["task-memory:quarantined"]


def test_task_memory_prepare_context_touches_access_metadata() -> None:
    store = InMemoryTaskMemoryStore()
    store.put_record(_task_memory_record("active", status=TaskMemoryRecordStatus.ACTIVE))
    runtime = TaskMemoryRuntime(store=store)
    orchestrator = TaskOrchestratorService(memory_runtime=runtime)
    session = orchestrator.create_session(
        "Inspect governed memory",
        target_kind=EntityKind.RUN,
        target_id="run-123",
        verification_spec=_verification_spec(),
    )

    context = runtime.prepare_context(session, role=AgentRole.PLANNER)
    touched = store.get_record("task-memory:active")

    assert context.matches
    assert touched is not None
    assert touched.access_count == 1
    assert touched.last_accessed_at_ms is not None


def test_sqlite_task_memory_store_migrates_v1_records_to_v2(artifact_tmp_path: Path) -> None:
    path = sqlite_path(artifact_tmp_path, "task-memory-v1")
    legacy_payload = _task_memory_record("legacy", status=TaskMemoryRecordStatus.ACTIVE).model_dump(mode="json")
    for field_name in (
        "status",
        "version",
        "expires_at_ms",
        "superseded_by",
        "last_accessed_at_ms",
        "access_count",
        "quality_decision",
        "governance_tags",
    ):
        legacy_payload.pop(field_name, None)
    connection = sqlite3.connect(path)
    with connection:
        connection.execute(
            """
            CREATE TABLE task_memory_records (
                memory_id TEXT PRIMARY KEY,
                schema_version INTEGER NOT NULL,
                kind TEXT NOT NULL,
                role_scope TEXT,
                target_kind TEXT,
                target_id TEXT,
                verdict_status TEXT,
                blocked_reason TEXT,
                created_at_ms INTEGER NOT NULL,
                updated_at_ms INTEGER NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO task_memory_records (
                memory_id, schema_version, kind, role_scope, target_kind, target_id,
                verdict_status, blocked_reason, created_at_ms, updated_at_ms, payload
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                legacy_payload["memory_id"],
                1,
                legacy_payload["kind"],
                legacy_payload["role_scope"],
                legacy_payload["target_kind"],
                legacy_payload["target_id"],
                legacy_payload["verdict_status"],
                legacy_payload["blocked_reason"],
                legacy_payload["created_at_ms"],
                legacy_payload["updated_at_ms"],
                json.dumps(legacy_payload),
            ),
        )
    connection.close()

    with SqliteTaskMemoryStore(str(path)) as store:
        restored = store.get_record("task-memory:legacy")
        matches = store.query_records(TaskMemoryQuery(goal_text="Inspect governed memory"))

    assert restored is not None
    assert restored.status == TaskMemoryRecordStatus.ACTIVE
    assert matches and matches[0].memory_id == "task-memory:legacy"


def _task_memory_record(
    suffix: str,
    *,
    status: TaskMemoryRecordStatus,
    expires_at_ms: int | None = None,
) -> TaskMemoryRecord:
    return TaskMemoryRecord(
        memory_id=f"task-memory:{suffix}",
        kind=TaskMemoryRecordKind.TASK_OUTCOME,
        source="test",
        goal="Inspect governed memory",
        target_kind=EntityKind.RUN,
        target_id="run-123",
        role_scope=AgentRole.PLANNER.value,
        verdict_status=VerificationStatus.VERIFIED_SUCCESS,
        summary="Governed memory inspection completed successfully.",
        tags=["planner", "governed"],
        evidence_ref_ids=["evidence:governed"],
        proposal_fingerprint="governed",
        content_payload={"audit_id": "audit:governed"},
        created_at_ms=1,
        updated_at_ms=1,
        status=status,
        expires_at_ms=expires_at_ms,
    )
