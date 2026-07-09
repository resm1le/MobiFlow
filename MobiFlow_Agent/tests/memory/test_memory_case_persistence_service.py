from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import pytest

from tests.artifacts import artifact_dir

from mobiflow_agent.common.contracts import EntityKind, EvidenceKind, EvidenceRef, VerificationStatus, VerificationVerdict
from mobiflow_agent.execution.recovery.models import GovernedRecoveryExecutionResponse
from mobiflow_agent.memory.case import (
    RecoveryCaseQuery,
    RecoveryMemoryCase,
)
from mobiflow_agent.memory.catalog import (
    MemoryCaseDocumentSchemaVersion,
    RecoveryMemoryCaseCatalog,
    RecoveryMemoryCaseCatalogEntry,
    RecoveryMemoryCaseDocument,
)
from mobiflow_agent.memory.catalog import MemoryCasePersistenceService
from mobiflow_agent.memory.case import MemoryCaseRetrievalService
from mobiflow_agent.execution.followup.decisions import RecoveryFollowupDriverDecision
from tests.harness_helpers import build_task_harness_response
from mobiflow_agent.evaluation.replay import RecoveryReplayCase
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
    category: str = "followup",
    action_name: str = "create_run",
    decision: RecoveryFollowupDriverDecision = RecoveryFollowupDriverDecision.COMPLETE,
    verdict_status: VerificationStatus | None = VerificationStatus.VERIFIED_SUCCESS,
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


def _test_dir(artifact_tmp_path: Path, name: str) -> Path:
    return artifact_dir(artifact_tmp_path, name)


def test_save_case_writes_utf8_json_document(artifact_tmp_path) -> None:
    service = MemoryCasePersistenceService()
    case = _memory_case(case_id="memory:alpha", tags=["device", "稳定"])
    output_path = _test_dir(artifact_tmp_path, "save-case") / "nested" / "case.json"

    entry = service.save_case(case=case, output_path=str(output_path))

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == MemoryCaseDocumentSchemaVersion.V1.value
    assert payload["case"]["case_id"] == "memory:alpha"
    assert payload["case"]["tags"] == ["device", "稳定"]
    assert entry.case_id == "memory:alpha"
    assert entry.summary == "memory:alpha summary"


def test_load_case_restores_recovery_memory_case(artifact_tmp_path) -> None:
    service = MemoryCasePersistenceService()
    case = _memory_case(case_id="memory:load", action_name="create_single_device_run")
    output_path = _test_dir(artifact_tmp_path, "load-case") / "case.json"
    service.save_case(case=case, output_path=str(output_path))

    restored = service.load_case(str(output_path))

    assert restored.case_id == case.case_id
    assert restored.action_name == "create_single_device_run"
    assert restored.replay_case.case_id == case.replay_case.case_id


def test_memory_case_document_and_catalog_entry_support_roundtrip() -> None:
    case = _memory_case(case_id="memory:roundtrip", tags=["stable"])
    document = RecoveryMemoryCaseDocument(case=case)
    entry = RecoveryMemoryCaseCatalogEntry(
        case_id=case.case_id,
        source=case.source,
        category=case.category,
        action_name=case.action_name,
        decision=case.decision,
        verdict_status=case.verdict_status,
        tags=case.tags,
        path="memory%3Aroundtrip.json",
        summary=case.input_summary,
    )

    restored_document = RecoveryMemoryCaseDocument.model_validate(document.model_dump(mode="python"))
    restored_entry = RecoveryMemoryCaseCatalogEntry.model_validate(entry.model_dump(mode="python"))

    assert restored_document.schema_version == MemoryCaseDocumentSchemaVersion.V1
    assert restored_document.case.case_id == "memory:roundtrip"
    assert restored_entry.case_id == "memory:roundtrip"
    assert restored_entry.tags == ["stable"]


def test_save_to_catalog_writes_case_id_named_file_and_preserves_full_case_id(artifact_tmp_path) -> None:
    service = MemoryCasePersistenceService()
    catalog_dir = _test_dir(artifact_tmp_path, "save-to-catalog")
    case = _memory_case(case_id="memory:case/alpha")

    entry = service.save_to_catalog(case=case, catalog_dir=str(catalog_dir))

    expected_path = catalog_dir / f"{quote(case.case_id, safe='-_')}.json"
    assert entry.path == str(expected_path)
    assert entry.case_id == "memory:case/alpha"
    assert expected_path.exists()


def test_list_catalog_scans_json_files_and_sorts_by_case_id(artifact_tmp_path) -> None:
    service = MemoryCasePersistenceService()
    catalog_dir = _test_dir(artifact_tmp_path, "list-catalog")
    second = _memory_case(case_id="memory:b")
    first = _memory_case(case_id="memory:a")
    service.save_to_catalog(case=second, catalog_dir=str(catalog_dir))
    service.save_to_catalog(case=first, catalog_dir=str(catalog_dir))
    (catalog_dir / "ignored.txt").write_text("not a memory case", encoding="utf-8")

    catalog = service.list_catalog(str(catalog_dir))

    assert isinstance(catalog, RecoveryMemoryCaseCatalog)
    assert [entry.case_id for entry in catalog.entries] == ["memory:a", "memory:b"]


def test_load_from_catalog_reads_case_by_case_id(artifact_tmp_path) -> None:
    service = MemoryCasePersistenceService()
    catalog_dir = _test_dir(artifact_tmp_path, "load-from-catalog")
    case = _memory_case(case_id="memory:load-from-catalog", category="device-recovery")
    service.save_to_catalog(case=case, catalog_dir=str(catalog_dir))

    restored = service.load_from_catalog(
        catalog_dir=str(catalog_dir),
        case_id="memory:load-from-catalog",
    )

    assert restored.case_id == "memory:load-from-catalog"
    assert restored.category == "device-recovery"


def test_retrieve_from_catalog_reuses_deterministic_retrieval_order_and_limit(artifact_tmp_path) -> None:
    service = MemoryCasePersistenceService()
    catalog_dir = _test_dir(artifact_tmp_path, "retrieve-from-catalog")
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
    unrelated = _memory_case(
        case_id="memory:c",
        category="followup",
        action_name="cancel_run",
        decision=RecoveryFollowupDriverDecision.COMPLETE,
        verdict_status=VerificationStatus.VERIFIED_SUCCESS,
    )
    for case in [unrelated, weaker, strongest]:
        service.save_to_catalog(case=case, catalog_dir=str(catalog_dir))

    response = service.retrieve_from_catalog(
        catalog_dir=str(catalog_dir),
        query=RecoveryCaseQuery(
            category="followup",
            action_name="create_run",
            verdict_status=VerificationStatus.VERIFIED_SUCCESS,
            tags=["priority", "device"],
            limit=2,
        ),
    )

    assert [match.case.case_id for match in response.matches] == ["memory:a", "memory:b"]
    assert len(response.matches) == 2


def test_empty_catalog_lists_empty_entries_and_retrieval_returns_no_matches(artifact_tmp_path) -> None:
    service = MemoryCasePersistenceService()
    catalog_dir = _test_dir(artifact_tmp_path, "empty")

    catalog = service.list_catalog(str(catalog_dir))
    response = service.retrieve_from_catalog(
        catalog_dir=str(catalog_dir),
        query=RecoveryCaseQuery(action_name="create_run"),
    )

    assert catalog.entries == []
    assert response.matches == []
    assert "No recovery memory cases matched" in response.summary


def test_missing_catalog_directory_raises_file_not_found(artifact_tmp_path) -> None:
    missing_dir = _test_dir(artifact_tmp_path, "missing").parent / f"missing-{uuid4().hex}"

    with pytest.raises(FileNotFoundError, match="Memory case catalog directory does not exist"):
        MemoryCasePersistenceService().list_catalog(str(missing_dir))


def test_load_case_rejects_invalid_json(artifact_tmp_path) -> None:
    path = _test_dir(artifact_tmp_path, "bad-json") / "invalid.json"
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid memory case JSON document"):
        MemoryCasePersistenceService().load_case(str(path))


def test_load_case_rejects_unsupported_schema_version(artifact_tmp_path) -> None:
    path = _test_dir(artifact_tmp_path, "bad-schema") / "bad-schema.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "v999",
                "case": _memory_case(case_id="memory:bad-schema").model_dump(mode="json"),
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Invalid memory case document schema"):
        MemoryCasePersistenceService().load_case(str(path))


def test_list_catalog_rejects_invalid_case_document_structure(artifact_tmp_path) -> None:
    catalog_dir = _test_dir(artifact_tmp_path, "invalid-catalog")
    invalid_path = catalog_dir / "broken.json"
    invalid_path.write_text(
        json.dumps({"schema_version": "v1", "case": {"oops": True}}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Invalid memory case document schema"):
        MemoryCasePersistenceService().list_catalog(str(catalog_dir))


def test_persistence_layer_is_static_and_uses_only_memory_cases(artifact_tmp_path) -> None:
    service = MemoryCasePersistenceService()
    catalog_dir = _test_dir(artifact_tmp_path, "static")
    case = _memory_case(
        case_id="memory:static",
        decision=RecoveryFollowupDriverDecision.HANDOFF_ONLY,
        verdict_status=VerificationStatus.BLOCKED,
        tags=["blocked"],
    )

    entry = service.save_to_catalog(case=case, catalog_dir=str(catalog_dir))
    restored = service.load_case(entry.path)
    response = service.retrieve_from_catalog(
        catalog_dir=str(catalog_dir),
        query=RecoveryCaseQuery(tags=["blocked"]),
    )

    assert restored.case_id == "memory:static"
    assert response.matches[0].case.case_id == "memory:static"
    assert response.matches[0].case.replay_case == case.replay_case


