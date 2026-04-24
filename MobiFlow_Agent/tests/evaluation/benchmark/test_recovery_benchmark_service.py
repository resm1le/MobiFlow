from __future__ import annotations

import pytest

from mobiflow_agent.common.contracts import EntityKind, EvidenceKind, EvidenceRef, VerificationStatus, VerificationVerdict
from mobiflow_agent.execution.recovery.execution import GovernedRecoveryExecutionResponse
from mobiflow_agent.memory.case import MemoryCaseRetrievalService
from mobiflow_agent.evaluation.benchmark.suite import (
    RecoveryBenchmarkCase,
    RecoveryBenchmarkSchemaVersion,
    RecoveryBenchmarkSuite,
)
from mobiflow_agent.evaluation.benchmark.suite import RecoveryBenchmarkService
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
    verdict_status: VerificationStatus = VerificationStatus.VERIFIED_SUCCESS,
) -> GovernedRecoveryExecutionResponse:
    verdict = _verdict(verdict_status, summary=f"{action_name} completed")
    return GovernedRecoveryExecutionResponse(
        thread_id="thread-1",
        run_target_id="rt-1",
        run_id="run-1",
        action_name=action_name,
        created_run_id="run-created",
        followup_required=True,
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


def _eval_case(
    *,
    case_id: str = "eval:test",
    expected_decision: RecoveryFollowupDriverDecision | None = RecoveryFollowupDriverDecision.COMPLETE,
    expected_verdict_status: VerificationStatus | None = VerificationStatus.VERIFIED_SUCCESS,
    actual_decision: RecoveryFollowupDriverDecision = RecoveryFollowupDriverDecision.COMPLETE,
    actual_verdict_status: VerificationStatus | None = VerificationStatus.VERIFIED_SUCCESS,
) -> RecoveryEvalCase:
    return RecoveryEvalCase(
        case_id=case_id,
        category="recovery-followup",
        input_summary=f"{case_id} summary",
        expected_decision=expected_decision,
        expected_verdict_status=expected_verdict_status,
        replay_case=RecoveryReplayCase(
            case_id=f"replay:{case_id}",
            source="test",
            execution=_execution_response(),
            harness_response=_harness_response(
                decision=actual_decision,
                verdict_status=actual_verdict_status,
            ),
        ),
    )


def test_build_case_creates_versioned_benchmark_case() -> None:
    service = RecoveryBenchmarkService()

    benchmark_case = service.build_case(
        source="manual",
        eval_case=_eval_case(),
    )

    assert benchmark_case.schema_version == RecoveryBenchmarkSchemaVersion.V1
    assert benchmark_case.benchmark_case_id.startswith("benchmark-case:")
    assert benchmark_case.category == "recovery-followup"


def test_build_case_allows_missing_memory_case() -> None:
    service = RecoveryBenchmarkService()

    benchmark_case = service.build_case(
        source="manual",
        eval_case=_eval_case(),
        memory_case=None,
    )

    assert benchmark_case.memory_case is None


def test_benchmark_case_supports_roundtrip() -> None:
    service = RecoveryBenchmarkService()
    memory_case = MemoryCaseRetrievalService().build_case(
        source="manual",
        replay_case=_eval_case().replay_case,
        category="recovery-followup",
        input_summary="memory case",
    )
    benchmark_case = service.build_case(
        source="manual",
        eval_case=_eval_case(),
        memory_case=memory_case,
    )

    restored = RecoveryBenchmarkCase.model_validate(benchmark_case.model_dump(mode="python"))

    assert restored.schema_version == RecoveryBenchmarkSchemaVersion.V1
    assert restored.memory_case is not None
    assert restored.eval_case.case_id.startswith("eval:")


def test_benchmark_suite_supports_roundtrip() -> None:
    service = RecoveryBenchmarkService()
    suite = service.build_suite(
        name="regression-suite",
        cases=[service.build_case(source="manual", eval_case=_eval_case())],
    )

    restored = RecoveryBenchmarkSuite.model_validate(suite.model_dump(mode="python"))

    assert restored.schema_version == RecoveryBenchmarkSchemaVersion.V1
    assert restored.name == "regression-suite"
    assert len(restored.cases) == 1


def test_build_suite_rejects_empty_cases() -> None:
    service = RecoveryBenchmarkService()

    with pytest.raises(ValueError, match="at least one case"):
        service.build_suite(name="empty-suite", cases=[])


def test_run_suite_all_matched_returns_full_match_report() -> None:
    service = RecoveryBenchmarkService()
    suite = service.build_suite(
        name="all-pass",
        cases=[
            service.build_case(source="manual", eval_case=_eval_case(case_id="eval:1")),
            service.build_case(source="manual", eval_case=_eval_case(case_id="eval:2")),
        ],
    )

    report = service.run_suite(suite)

    assert report.total_cases == 2
    assert report.matched_cases == 2
    assert report.mismatched_cases == 0
    assert report.match_rate == 1.0


def test_run_suite_partial_mismatch_returns_aggregated_counts() -> None:
    service = RecoveryBenchmarkService()
    suite = service.build_suite(
        name="partial-pass",
        cases=[
            service.build_case(source="manual", eval_case=_eval_case(case_id="eval:1")),
            service.build_case(
                source="manual",
                eval_case=_eval_case(
                    case_id="eval:2",
                    expected_verdict_status=VerificationStatus.VERIFIED_SUCCESS,
                    actual_verdict_status=VerificationStatus.VERIFIED_FAILED,
                ),
            ),
        ],
    )

    report = service.run_suite(suite)

    assert report.total_cases == 2
    assert report.matched_cases == 1
    assert report.mismatched_cases == 1
    assert report.match_rate == 0.5


def test_run_suite_preserves_suite_case_order() -> None:
    service = RecoveryBenchmarkService()
    first = service.build_case(source="manual", eval_case=_eval_case(case_id="eval:first"))
    second = service.build_case(
        source="manual",
        eval_case=_eval_case(
            case_id="eval:second",
            expected_decision=RecoveryFollowupDriverDecision.COMPLETE,
            actual_decision=RecoveryFollowupDriverDecision.HANDOFF_ONLY,
        ),
    )
    suite = service.build_suite(name="ordered", cases=[first, second])

    report = service.run_suite(suite)

    assert [result.case_id for result in report.results] == ["eval:first", "eval:second"]


def test_benchmark_service_is_pure_and_requires_no_platform_calls() -> None:
    service = RecoveryBenchmarkService()
    eval_case = _eval_case(case_id="eval:pure")
    memory_case = MemoryCaseRetrievalService().build_case(
        source="manual",
        replay_case=eval_case.replay_case,
        eval_case=eval_case,
        category="recovery-followup",
        input_summary="pure memory case",
        tags=["stable"],
    )
    suite = service.build_suite(
        name="pure-suite",
        cases=[service.build_case(source="manual", eval_case=eval_case, memory_case=memory_case)],
    )

    report = service.run_suite(suite)

    assert suite.cases[0].eval_case is eval_case
    assert suite.cases[0].memory_case is memory_case
    assert report.results[0].case_id == "eval:pure"
    assert report.matched_cases == 1



