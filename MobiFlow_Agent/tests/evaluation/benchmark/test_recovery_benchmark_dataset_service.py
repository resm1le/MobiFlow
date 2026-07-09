from __future__ import annotations

import pytest

from mobiflow_agent.common.contracts import EntityKind, EvidenceKind, EvidenceRef, VerificationStatus, VerificationVerdict
from mobiflow_agent.execution.recovery.execution import GovernedRecoveryExecutionResponse
from mobiflow_agent.memory.case import MemoryCaseRetrievalService
from mobiflow_agent.evaluation.benchmark.dataset import (
    RecoveryBenchmarkDataset,
    RecoveryBenchmarkDatasetSchemaVersion,
)
from mobiflow_agent.evaluation.benchmark.dataset import RecoveryBenchmarkDatasetService
from mobiflow_agent.evaluation.benchmark.suite import RecoveryBenchmarkService
from mobiflow_agent.execution.followup.decisions import RecoveryFollowupDriverDecision
from tests.harness_helpers import build_task_harness_response
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
):
    replay_eval_service = ReplayEvalService()
    execution = _execution_response()
    harness_response = _harness_response(
        decision=actual_decision,
        verdict_status=actual_verdict_status,
    )
    return replay_eval_service.build_eval_case(
        category="recovery-followup",
        input_summary=f"{case_id} summary",
        execution=execution,
        harness_response=harness_response,
        expected_decision=expected_decision,
        expected_verdict_status=expected_verdict_status,
    ).model_copy(update={"case_id": case_id})


def _benchmark_suite(case_id: str, *, matched: bool = True):
    benchmark_service = RecoveryBenchmarkService()
    eval_case = _eval_case(
        case_id=case_id,
        expected_verdict_status=VerificationStatus.VERIFIED_SUCCESS,
        actual_verdict_status=(
            VerificationStatus.VERIFIED_SUCCESS if matched else VerificationStatus.VERIFIED_FAILED
        ),
    )
    memory_case = MemoryCaseRetrievalService().build_case(
        source="manual",
        replay_case=eval_case.replay_case,
        eval_case=eval_case,
        category="recovery-followup",
        input_summary=f"{case_id} memory",
        tags=["benchmark"],
    )
    benchmark_case = benchmark_service.build_case(
        source="manual",
        eval_case=eval_case,
        memory_case=memory_case,
    )
    return benchmark_service.build_suite(
        name=f"suite-{case_id}",
        cases=[benchmark_case],
    )


def test_build_dataset_creates_versioned_dataset_from_multiple_suites() -> None:
    service = RecoveryBenchmarkDatasetService()
    first_suite = _benchmark_suite("eval:1")
    second_suite = _benchmark_suite("eval:2")

    dataset = service.build_dataset(
        name="dataset-alpha",
        source="manual",
        suites=[first_suite, second_suite],
    )

    assert dataset.schema_version == RecoveryBenchmarkDatasetSchemaVersion.V1
    assert dataset.dataset_id.startswith("benchmark-dataset:")
    assert [suite.suite_id for suite in dataset.suites] == [first_suite.suite_id, second_suite.suite_id]


def test_benchmark_dataset_supports_roundtrip() -> None:
    service = RecoveryBenchmarkDatasetService()
    dataset = service.build_dataset(
        name="dataset-roundtrip",
        source="manual",
        suites=[_benchmark_suite("eval:rt")],
    )

    restored = RecoveryBenchmarkDataset.model_validate(dataset.model_dump(mode="python"))

    assert restored.schema_version == RecoveryBenchmarkDatasetSchemaVersion.V1
    assert restored.name == "dataset-roundtrip"
    assert len(restored.suites) == 1


def test_build_dataset_rejects_empty_suites() -> None:
    service = RecoveryBenchmarkDatasetService()

    with pytest.raises(ValueError, match="at least one suite"):
        service.build_dataset(name="empty", source="manual", suites=[])


def test_run_dataset_all_matched_returns_full_match_report() -> None:
    service = RecoveryBenchmarkDatasetService()
    dataset = service.build_dataset(
        name="all-pass",
        source="manual",
        suites=[_benchmark_suite("eval:1"), _benchmark_suite("eval:2")],
    )

    report = service.run_dataset(dataset)

    assert report.total_suites == 2
    assert report.total_cases == 2
    assert report.matched_cases == 2
    assert report.mismatched_cases == 0
    assert report.match_rate == 1.0


def test_run_dataset_partial_mismatch_returns_aggregated_counts() -> None:
    service = RecoveryBenchmarkDatasetService()
    dataset = service.build_dataset(
        name="partial-pass",
        source="manual",
        suites=[_benchmark_suite("eval:1"), _benchmark_suite("eval:2", matched=False)],
    )

    report = service.run_dataset(dataset)

    assert report.total_suites == 2
    assert report.total_cases == 2
    assert report.matched_cases == 1
    assert report.mismatched_cases == 1
    assert report.match_rate == 0.5


def test_run_dataset_preserves_suite_order() -> None:
    service = RecoveryBenchmarkDatasetService()
    first_suite = _benchmark_suite("eval:first")
    second_suite = _benchmark_suite("eval:second", matched=False)
    dataset = service.build_dataset(
        name="ordered",
        source="manual",
        suites=[first_suite, second_suite],
    )

    report = service.run_dataset(dataset)

    assert [suite_report.suite_id for suite_report in report.suite_reports] == [
        first_suite.suite_id,
        second_suite.suite_id,
    ]


def test_benchmark_dataset_service_is_pure_and_requires_no_platform_calls() -> None:
    service = RecoveryBenchmarkDatasetService()
    suite = _benchmark_suite("eval:pure")
    dataset = service.build_dataset(
        name="pure",
        source="manual",
        suites=[suite],
    )

    report = service.run_dataset(dataset)

    assert dataset.suites[0] is suite
    assert report.suite_reports[0].suite_id == suite.suite_id
    assert report.matched_cases == 1



