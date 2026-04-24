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
from mobiflow_agent.runtime import ContextCompressionPolicy, ContextCompressionService
from mobiflow_agent.task.plan import TaskPlan, TaskStatus, TaskStep, TaskStepKind
from mobiflow_agent.task.session import TaskSession


def _session() -> TaskSession:
    step = TaskStep(
        step_id="step-1",
        kind=TaskStepKind.VERIFY,
        goal="Verify the run outcome",
        expected_outputs=["verification_verdict"],
        verification_target_kind=EntityKind.RUN,
        verification_target_id="run-123",
        verification_spec=VerificationSpec(
            verification_id="verification:run:run-123",
            target_kind=EntityKind.RUN,
            target_id="run-123",
            success_checks=[
                VerificationCheck(
                    check_id="run-healthy",
                    description="The run stays healthy.",
                    evidence_hint="healthy",
                )
            ],
        ),
    )
    return TaskSession(
        session_id="session-1",
        goal="Inspect blocked task",
        status=TaskStatus.VERIFYING,
        target_kind=EntityKind.RUN,
        target_id="run-123",
        plan=TaskPlan(plan_id="plan-1", summary="verify", steps=[step]),
        current_step_index=0,
        current_step=step,
        active_verification_spec=step.verification_spec,
        last_observation=ObservationView(
            observation_id="obs-1",
            focus_kind=EntityKind.RUN,
            focus_id="run-123",
            facts=[
                ObservationFact(
                    fact_id="fact-1",
                    source=ObservationFactSource.PLATFORM,
                    title="Run status",
                    value={"status": "healthy", "detail": "x" * 600},
                    evidence_refs=[
                        EvidenceRef(
                            evidence_id="evidence-1",
                            kind=EvidenceKind.PLATFORM_SNAPSHOT,
                            summary="Run is healthy.",
                            locator="run-123",
                        )
                    ],
                )
            ],
        ),
        last_verdict=VerificationVerdict(
            verdict_id="verdict-1",
            status=VerificationStatus.VERIFIED_SUCCESS,
            summary="Run is healthy.",
            target_kind=EntityKind.RUN,
            target_id="run-123",
            matched_check_ids=["run-healthy"],
            evidence_refs=[
                EvidenceRef(
                    evidence_id="evidence-1",
                    kind=EvidenceKind.PLATFORM_SNAPSHOT,
                    summary="Run is healthy.",
                    locator="run-123",
                )
            ],
        ),
        memory_context={"step-1": {"detail": "m" * 500, "items": list(range(20))}},
        evaluation_context={"step-1": {"detail": "e" * 500, "items": list(range(20))}},
    )


def test_context_compression_service_refreshes_digest_and_exports_handoff() -> None:
    service = ContextCompressionService()
    session = _session()

    service.refresh_session_context(session)
    handoff = service.export_context_handoff(session)
    restored = service.apply_context_handoff(
        TaskSession(session_id="session-2", goal="Inspect blocked task"),
        handoff,
    )

    assert session.step_summaries["step-1"].matched_check_ids == ["run-healthy"]
    assert session.session_digest is not None
    assert session.session_digest.context_token_estimate > 0
    assert handoff.session_digest.summary
    assert restored.imported_handoff is not None
    assert restored.session_digest is not None


def test_context_compression_service_preserves_current_observation_when_compacting_prompt() -> None:
    service = ContextCompressionService(
        policy=ContextCompressionPolicy(max_string_chars=48, max_list_items=2, max_dict_items=2)
    )
    session = _session()
    service.refresh_session_context(session)

    result = service.compact_prompt(
        system_prompt="system",
        payload={
            "goal": session.goal,
            "active_verification_spec": session.active_verification_spec.model_dump(mode="python"),
            "observation": session.last_observation.model_dump(mode="python"),
            "memory_context": session.memory_context,
            "evaluation_context": session.evaluation_context,
            "session_digest": session.session_digest.model_dump(mode="python"),
        },
        preserve_keys=["goal", "active_verification_spec", "observation"],
        input_token_budget=60,
        compaction_target_tokens=50,
    )

    assert result.compacted is True
    assert result.context_payload["observation"]["facts"][0]["evidence_refs"][0]["evidence_id"] == "evidence-1"
    assert result.estimated_input_tokens_after <= result.estimated_input_tokens_before
