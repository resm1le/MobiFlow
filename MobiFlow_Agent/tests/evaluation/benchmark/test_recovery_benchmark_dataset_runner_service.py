from __future__ import annotations

from pathlib import Path

from tests.artifacts import artifact_dir
from uuid import uuid4

from mobiflow_agent.common.contracts import EntityKind, EvidenceKind, EvidenceRef, VerificationStatus, VerificationVerdict
from mobiflow_agent.execution.recovery.execution import GovernedRecoveryExecutionResponse
from mobiflow_agent.memory.case import MemoryCaseRetrievalService
from mobiflow_agent.evaluation.benchmark.run_report import (
    RecoveryBenchmarkCatalogRunReport,
    RecoveryBenchmarkDatasetRunReport,
    RecoveryBenchmarkDatasetRunnerSchemaVersion,
)
from mobiflow_agent.evaluation.benchmark.run_report import (
    RecoveryBenchmarkDatasetRunnerService,
)
from mobiflow_agent.evaluation.benchmark.dataset_catalog import (
    RecoveryBenchmarkDatasetPersistenceService,
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
    case_id: str,
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


def _dataset(case_id: str, *, matched: bool = True):
    return RecoveryBenchmarkDatasetService().build_dataset(
        name=f"dataset-{case_id}",
        source="manual",
        suites=[_benchmark_suite(case_id, matched=matched)],
    )


def _test_dir(artifact_tmp_path: Path, name: str) -> Path:
    return artifact_dir(artifact_tmp_path, name)


def test_run_dataset_builds_versioned_dataset_report() -> None:
    service = RecoveryBenchmarkDatasetRunnerService()
    dataset = _dataset("eval:runner")

    report = service.run_dataset(dataset)

    assert report.schema_version == RecoveryBenchmarkDatasetRunnerSchemaVersion.V1
    assert report.dataset_id == dataset.dataset_id
    assert report.dataset_name == dataset.name
    assert report.source_path is None
    assert report.result.total_suites == 1


def test_run_dataset_file_loads_dataset_and_sets_absolute_source_path(artifact_tmp_path) -> None:
    persistence = RecoveryBenchmarkDatasetPersistenceService()
    service = RecoveryBenchmarkDatasetRunnerService()
    dataset = _dataset("eval:file")
    tmp_path = _test_dir(artifact_tmp_path, "dataset-file")
    output_path = tmp_path / "dataset.json"
    persistence.save_dataset(dataset=dataset, output_path=str(output_path))

    report = service.run_dataset_file(str(output_path))

    assert report.dataset_id == dataset.dataset_id
    assert report.source_path == str(output_path.resolve())
    assert report.result.matched_cases == 1


def test_run_catalog_runs_datasets_in_dataset_id_order(artifact_tmp_path) -> None:
    persistence = RecoveryBenchmarkDatasetPersistenceService()
    service = RecoveryBenchmarkDatasetRunnerService()
    tmp_path = _test_dir(artifact_tmp_path, "catalog-order")
    first = _dataset("eval:b").model_copy(update={"dataset_id": "benchmark-dataset:b"})
    second = _dataset("eval:a").model_copy(update={"dataset_id": "benchmark-dataset:a"})
    persistence.save_to_catalog(dataset=first, catalog_dir=str(tmp_path))
    persistence.save_to_catalog(dataset=second, catalog_dir=str(tmp_path))

    report = service.run_catalog(str(tmp_path))

    assert [item.dataset_id for item in report.dataset_reports] == [
        "benchmark-dataset:a",
        "benchmark-dataset:b",
    ]
    assert report.catalog_dir == str(tmp_path.resolve())


def test_run_catalog_all_matched_returns_full_match_aggregation(artifact_tmp_path) -> None:
    persistence = RecoveryBenchmarkDatasetPersistenceService()
    service = RecoveryBenchmarkDatasetRunnerService()
    tmp_path = _test_dir(artifact_tmp_path, "catalog-all-pass")
    persistence.save_to_catalog(dataset=_dataset("eval:1"), catalog_dir=str(tmp_path))
    persistence.save_to_catalog(dataset=_dataset("eval:2"), catalog_dir=str(tmp_path))

    report = service.run_catalog(str(tmp_path))

    assert report.total_datasets == 2
    assert report.total_suites == 2
    assert report.total_cases == 2
    assert report.matched_cases == 2
    assert report.mismatched_cases == 0
    assert report.match_rate == 1.0


def test_run_catalog_partial_mismatch_returns_correct_aggregates(artifact_tmp_path) -> None:
    persistence = RecoveryBenchmarkDatasetPersistenceService()
    service = RecoveryBenchmarkDatasetRunnerService()
    tmp_path = _test_dir(artifact_tmp_path, "catalog-partial-pass")
    persistence.save_to_catalog(dataset=_dataset("eval:1"), catalog_dir=str(tmp_path))
    persistence.save_to_catalog(dataset=_dataset("eval:2", matched=False), catalog_dir=str(tmp_path))

    report = service.run_catalog(str(tmp_path))

    assert report.total_datasets == 2
    assert report.total_cases == 2
    assert report.matched_cases == 1
    assert report.mismatched_cases == 1
    assert report.match_rate == 0.5


def test_run_catalog_dataset_runs_named_dataset_only(artifact_tmp_path) -> None:
    persistence = RecoveryBenchmarkDatasetPersistenceService()
    service = RecoveryBenchmarkDatasetRunnerService()
    tmp_path = _test_dir(artifact_tmp_path, "catalog-single")
    dataset = _dataset("eval:single")
    persistence.save_to_catalog(dataset=dataset, catalog_dir=str(tmp_path))

    report = service.run_catalog_dataset(
        catalog_dir=str(tmp_path),
        dataset_id=dataset.dataset_id,
    )

    assert report.dataset_id == dataset.dataset_id
    assert report.result.total_suites == 1
    assert report.result.total_cases == 1


def test_dataset_run_report_supports_roundtrip() -> None:
    service = RecoveryBenchmarkDatasetRunnerService()
    report = service.run_dataset(_dataset("eval:roundtrip"))

    restored = RecoveryBenchmarkDatasetRunReport.model_validate(report.model_dump(mode="python"))

    assert restored.schema_version == RecoveryBenchmarkDatasetRunnerSchemaVersion.V1
    assert restored.dataset_id == report.dataset_id


def test_catalog_run_report_supports_roundtrip(artifact_tmp_path) -> None:
    persistence = RecoveryBenchmarkDatasetPersistenceService()
    service = RecoveryBenchmarkDatasetRunnerService()
    tmp_path = _test_dir(artifact_tmp_path, "catalog-roundtrip")
    persistence.save_to_catalog(dataset=_dataset("eval:rt"), catalog_dir=str(tmp_path))
    report = service.run_catalog(str(tmp_path))

    restored = RecoveryBenchmarkCatalogRunReport.model_validate(report.model_dump(mode="python"))

    assert restored.schema_version == RecoveryBenchmarkDatasetRunnerSchemaVersion.V1
    assert restored.total_datasets == 1


def test_runner_layer_is_static_and_reuses_existing_benchmark_aggregation(artifact_tmp_path) -> None:
    persistence = RecoveryBenchmarkDatasetPersistenceService()
    service = RecoveryBenchmarkDatasetRunnerService()
    tmp_path = _test_dir(artifact_tmp_path, "runner-static")
    dataset = _dataset("eval:static", matched=False)
    persistence.save_to_catalog(dataset=dataset, catalog_dir=str(tmp_path))

    report = service.run_catalog(str(tmp_path))

    assert report.dataset_reports[0].dataset_id == dataset.dataset_id
    assert report.dataset_reports[0].result.suite_reports[0].suite_id == dataset.suites[0].suite_id
    assert report.mismatched_cases == 1



