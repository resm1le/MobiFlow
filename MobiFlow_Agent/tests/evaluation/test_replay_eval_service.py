from __future__ import annotations

from mobiflow_agent.common.contracts import EntityKind, EvidenceKind, EvidenceRef, VerificationStatus, VerificationVerdict
from mobiflow_agent.execution.recovery.models import GovernedRecoveryExecutionResponse
from mobiflow_agent.execution.followup.decisions import RecoveryFollowupDriverDecision
from tests.harness_helpers import build_task_harness_response
from mobiflow_agent.evaluation.replay import (
    ReplayEvalSchemaVersion,
    RecoveryEvalCase,
    RecoveryReplayCase,
)
from mobiflow_agent.evaluation.replay import ReplayEvalService
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


def test_build_replay_case_creates_versioned_case() -> None:
    service = ReplayEvalService()

    replay_case = service.build_replay_case(
        source="heartbeat-driver-harness",
        execution=_execution_response(),
        harness_response=_harness_response(),
    )

    assert replay_case.schema_version == ReplayEvalSchemaVersion.V1
    assert replay_case.case_id.startswith("replay:")
    assert replay_case.source == "heartbeat-driver-harness"


def test_build_eval_case_preserves_expected_decision() -> None:
    service = ReplayEvalService()

    eval_case = service.build_eval_case(
        category="followup",
        input_summary="create_run followup should continue polling",
        execution=_execution_response(),
        harness_response=_harness_response(decision=RecoveryFollowupDriverDecision.SCHEDULE_NEXT, verdict_status=None),
        expected_decision=RecoveryFollowupDriverDecision.SCHEDULE_NEXT,
    )

    assert eval_case.expected_decision == RecoveryFollowupDriverDecision.SCHEDULE_NEXT
    assert eval_case.replay_case.harness_response.decision == RecoveryFollowupDriverDecision.SCHEDULE_NEXT


def test_build_eval_case_preserves_expected_verdict_status() -> None:
    service = ReplayEvalService()

    eval_case = service.build_eval_case(
        category="followup",
        input_summary="create_run followup should verify success",
        execution=_execution_response(),
        harness_response=_harness_response(verdict_status=VerificationStatus.VERIFIED_SUCCESS),
        expected_verdict_status=VerificationStatus.VERIFIED_SUCCESS,
    )

    assert eval_case.expected_verdict_status == VerificationStatus.VERIFIED_SUCCESS


def test_recovery_replay_case_supports_roundtrip() -> None:
    replay_case = RecoveryReplayCase(
        case_id="replay:test",
        source="test",
        execution=_execution_response(),
        harness_response=_harness_response(),
    )

    restored = RecoveryReplayCase.model_validate(replay_case.model_dump(mode="python"))

    assert restored.schema_version == ReplayEvalSchemaVersion.V1
    assert restored.execution.run_target_id == "rt-1"
    assert restored.harness_response.decision == RecoveryFollowupDriverDecision.COMPLETE


def test_recovery_eval_case_supports_roundtrip() -> None:
    eval_case = RecoveryEvalCase(
        case_id="eval:test",
        category="followup",
        input_summary="test eval case",
        expected_decision=RecoveryFollowupDriverDecision.COMPLETE,
        expected_verdict_status=VerificationStatus.VERIFIED_SUCCESS,
        replay_case=RecoveryReplayCase(
            case_id="replay:test",
            source="test",
            execution=_execution_response(),
            harness_response=_harness_response(),
        ),
    )

    restored = RecoveryEvalCase.model_validate(eval_case.model_dump(mode="python"))

    assert restored.schema_version == ReplayEvalSchemaVersion.V1
    assert restored.expected_decision == RecoveryFollowupDriverDecision.COMPLETE
    assert restored.expected_verdict_status == VerificationStatus.VERIFIED_SUCCESS


def test_evaluate_returns_matched_true_when_decision_and_verdict_match() -> None:
    service = ReplayEvalService()
    case = service.build_eval_case(
        category="followup",
        input_summary="decision and verdict match",
        execution=_execution_response(),
        harness_response=_harness_response(
            decision=RecoveryFollowupDriverDecision.COMPLETE,
            verdict_status=VerificationStatus.VERIFIED_SUCCESS,
        ),
        expected_decision=RecoveryFollowupDriverDecision.COMPLETE,
        expected_verdict_status=VerificationStatus.VERIFIED_SUCCESS,
    )

    result = service.evaluate(case)

    assert result.matched is True
    assert result.actual_decision == RecoveryFollowupDriverDecision.COMPLETE
    assert result.actual_verdict_status == VerificationStatus.VERIFIED_SUCCESS


def test_evaluate_returns_matched_false_when_decision_mismatches() -> None:
    service = ReplayEvalService()
    case = service.build_eval_case(
        category="followup",
        input_summary="decision mismatch",
        execution=_execution_response(),
        harness_response=_harness_response(decision=RecoveryFollowupDriverDecision.HANDOFF_ONLY),
        expected_decision=RecoveryFollowupDriverDecision.COMPLETE,
    )

    result = service.evaluate(case)

    assert result.matched is False
    assert "decision expected complete but got handoff_only" in result.summary


def test_evaluate_returns_matched_false_when_verdict_mismatches() -> None:
    service = ReplayEvalService()
    case = service.build_eval_case(
        category="followup",
        input_summary="verdict mismatch",
        execution=_execution_response(),
        harness_response=_harness_response(verdict_status=VerificationStatus.VERIFIED_FAILED),
        expected_verdict_status=VerificationStatus.VERIFIED_SUCCESS,
    )

    result = service.evaluate(case)

    assert result.matched is False
    assert "verdict expected verified_success but got verified_failed" in result.summary


def test_evaluate_with_only_expected_decision_does_not_compare_verdict() -> None:
    service = ReplayEvalService()
    case = service.build_eval_case(
        category="followup",
        input_summary="decision only",
        execution=_execution_response(),
        harness_response=_harness_response(
            decision=RecoveryFollowupDriverDecision.SCHEDULE_NEXT,
            verdict_status=None,
        ),
        expected_decision=RecoveryFollowupDriverDecision.SCHEDULE_NEXT,
    )

    result = service.evaluate(case)

    assert result.matched is True
    assert result.actual_verdict_status is None


def test_evaluate_with_only_expected_verdict_does_not_compare_decision() -> None:
    service = ReplayEvalService()
    case = service.build_eval_case(
        category="followup",
        input_summary="verdict only",
        execution=_execution_response(),
        harness_response=_harness_response(
            decision=RecoveryFollowupDriverDecision.HANDOFF_ONLY,
            verdict_status=VerificationStatus.BLOCKED,
        ),
        expected_verdict_status=VerificationStatus.BLOCKED,
    )

    result = service.evaluate(case)

    assert result.matched is True
    assert result.actual_decision == RecoveryFollowupDriverDecision.HANDOFF_ONLY


def test_replay_eval_service_is_pure_and_does_not_call_platform_or_harness() -> None:
    service = ReplayEvalService()
    execution = _execution_response()
    harness_response = _harness_response()

    replay_case = service.build_replay_case(
        source="pure-test",
        execution=execution,
        harness_response=harness_response,
    )
    eval_case = service.build_eval_case(
        category="pure",
        input_summary="pure service",
        execution=execution,
        harness_response=harness_response,
        expected_decision=RecoveryFollowupDriverDecision.COMPLETE,
        expected_verdict_status=VerificationStatus.VERIFIED_SUCCESS,
    )
    result = service.evaluate(eval_case)

    assert replay_case.execution is execution
    assert replay_case.harness_response.summary == harness_response.summary
    assert eval_case.replay_case.execution is execution
    assert eval_case.replay_case.harness_response.summary == harness_response.summary
    assert result.matched is True



