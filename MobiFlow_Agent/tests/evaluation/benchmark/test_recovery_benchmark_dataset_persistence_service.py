from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import pytest

from tests.artifacts import artifact_dir

from mobiflow_agent.common.contracts import EntityKind, EvidenceKind, EvidenceRef, VerificationStatus, VerificationVerdict
from mobiflow_agent.execution.recovery.models import GovernedRecoveryExecutionResponse
from mobiflow_agent.memory.case import MemoryCaseRetrievalService
from mobiflow_agent.evaluation.benchmark.dataset_catalog import (
    RecoveryBenchmarkCatalog,
    RecoveryBenchmarkDatasetDocument,
    RecoveryBenchmarkDatasetDocumentSchemaVersion,
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


def _dataset(*, matched: bool = True):
    eval_case = _eval_case(
        case_id="eval:dataset",
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
        input_summary="memory case",
        tags=["dataset"],
    )
    benchmark_case = RecoveryBenchmarkService().build_case(
        source="manual",
        eval_case=eval_case,
        memory_case=memory_case,
    )
    benchmark_suite = RecoveryBenchmarkService().build_suite(
        name="suite-dataset",
        cases=[benchmark_case],
    )
    return RecoveryBenchmarkDatasetService().build_dataset(
        name="dataset-alpha",
        source="manual",
        suites=[benchmark_suite],
    )


def _test_dir(artifact_tmp_path: Path, name: str) -> Path:
    return artifact_dir(artifact_tmp_path, name)


def test_save_dataset_writes_json_document(artifact_tmp_path) -> None:
    service = RecoveryBenchmarkDatasetPersistenceService()
    dataset = _dataset()
    tmp_path = _test_dir(artifact_tmp_path, "save")
    output_path = tmp_path / "datasets" / "alpha.json"

    entry = service.save_dataset(dataset=dataset, output_path=str(output_path))

    assert output_path.exists()
    assert entry.dataset_id == dataset.dataset_id
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == RecoveryBenchmarkDatasetDocumentSchemaVersion.V1.value
    assert payload["dataset"]["dataset_id"] == dataset.dataset_id


def test_load_dataset_restores_dataset_from_json_file(artifact_tmp_path) -> None:
    service = RecoveryBenchmarkDatasetPersistenceService()
    dataset = _dataset()
    tmp_path = _test_dir(artifact_tmp_path, "load")
    output_path = tmp_path / "alpha.json"
    service.save_dataset(dataset=dataset, output_path=str(output_path))

    restored = service.load_dataset(str(output_path))

    assert restored.dataset_id == dataset.dataset_id
    assert restored.name == dataset.name
    assert len(restored.suites) == len(dataset.suites)


def test_dataset_document_supports_roundtrip() -> None:
    document = RecoveryBenchmarkDatasetDocument(dataset=_dataset())

    restored = RecoveryBenchmarkDatasetDocument.model_validate(document.model_dump(mode="python"))

    assert restored.schema_version == RecoveryBenchmarkDatasetDocumentSchemaVersion.V1
    assert restored.dataset.dataset_id == document.dataset.dataset_id


def test_save_dataset_creates_parent_directory(artifact_tmp_path) -> None:
    service = RecoveryBenchmarkDatasetPersistenceService()
    dataset = _dataset()
    tmp_path = _test_dir(artifact_tmp_path, "mkdir")
    output_path = tmp_path / "nested" / "catalog" / "dataset.json"

    service.save_dataset(dataset=dataset, output_path=str(output_path))

    assert output_path.parent.exists()
    assert output_path.exists()


def test_load_dataset_rejects_unsupported_schema_version(artifact_tmp_path) -> None:
    tmp_path = _test_dir(artifact_tmp_path, "bad-schema")
    path = tmp_path / "bad-schema.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "v999",
                "dataset": _dataset().model_dump(mode="json"),
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Invalid benchmark dataset document schema"):
        RecoveryBenchmarkDatasetPersistenceService().load_dataset(str(path))


def test_load_dataset_rejects_invalid_json(artifact_tmp_path) -> None:
    tmp_path = _test_dir(artifact_tmp_path, "bad-json")
    path = tmp_path / "invalid.json"
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid benchmark dataset JSON document"):
        RecoveryBenchmarkDatasetPersistenceService().load_dataset(str(path))


def test_save_to_catalog_writes_dataset_id_named_file(artifact_tmp_path) -> None:
    service = RecoveryBenchmarkDatasetPersistenceService()
    dataset = _dataset()
    tmp_path = _test_dir(artifact_tmp_path, "save-catalog")

    entry = service.save_to_catalog(dataset=dataset, catalog_dir=str(tmp_path))

    expected_path = tmp_path / f"{quote(dataset.dataset_id, safe='-_')}.json"
    assert entry.path == str(expected_path)
    assert expected_path.exists()


def test_list_catalog_returns_entries_sorted_by_dataset_id(artifact_tmp_path) -> None:
    service = RecoveryBenchmarkDatasetPersistenceService()
    tmp_path = _test_dir(artifact_tmp_path, "list-catalog")
    first = _dataset().model_copy(update={"dataset_id": "benchmark-dataset:b"})
    second = _dataset().model_copy(update={"dataset_id": "benchmark-dataset:a"})
    service.save_to_catalog(dataset=first, catalog_dir=str(tmp_path))
    service.save_to_catalog(dataset=second, catalog_dir=str(tmp_path))

    catalog = service.list_catalog(str(tmp_path))

    assert isinstance(catalog, RecoveryBenchmarkCatalog)
    assert [entry.dataset_id for entry in catalog.entries] == [
        "benchmark-dataset:a",
        "benchmark-dataset:b",
    ]


def test_load_from_catalog_reads_named_dataset(artifact_tmp_path) -> None:
    service = RecoveryBenchmarkDatasetPersistenceService()
    dataset = _dataset()
    tmp_path = _test_dir(artifact_tmp_path, "load-catalog")
    service.save_to_catalog(dataset=dataset, catalog_dir=str(tmp_path))

    restored = service.load_from_catalog(catalog_dir=str(tmp_path), dataset_id=dataset.dataset_id)

    assert restored.dataset_id == dataset.dataset_id
    assert restored.source == dataset.source


def test_list_catalog_rejects_invalid_dataset_document(artifact_tmp_path) -> None:
    tmp_path = _test_dir(artifact_tmp_path, "invalid-catalog")
    invalid_path = tmp_path / "broken.json"
    invalid_path.write_text(json.dumps({"schema_version": "v1", "dataset": {"oops": True}}), encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid benchmark dataset document schema"):
        RecoveryBenchmarkDatasetPersistenceService().list_catalog(str(tmp_path))


def test_persistence_service_is_pure_and_does_not_rerun_benchmark(artifact_tmp_path) -> None:
    service = RecoveryBenchmarkDatasetPersistenceService()
    dataset = _dataset(matched=False)
    tmp_path = _test_dir(artifact_tmp_path, "pure")
    entry = service.save_to_catalog(dataset=dataset, catalog_dir=str(tmp_path))

    catalog = service.list_catalog(str(tmp_path))
    restored = service.load_dataset(entry.path)

    assert catalog.entries[0].dataset_id == dataset.dataset_id
    assert catalog.entries[0].suite_count == len(dataset.suites)
    assert restored.dataset_id == dataset.dataset_id
    assert restored.suites[0].suite_id == dataset.suites[0].suite_id


def test_list_catalog_missing_directory_raises_file_not_found(artifact_tmp_path) -> None:
    tmp_path = _test_dir(artifact_tmp_path, "missing")
    missing_dir = tmp_path / "missing-catalog"

    with pytest.raises(FileNotFoundError):
        RecoveryBenchmarkDatasetPersistenceService().list_catalog(str(missing_dir))



