from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from tests.artifacts import artifact_dir

from mobiflow_agent.common.contracts import EntityKind, EvidenceKind, EvidenceRef, VerificationStatus, VerificationVerdict
from mobiflow_agent.execution.recovery.execution import GovernedRecoveryExecutionResponse
from mobiflow_agent.memory.case import RecoveryMemoryCase
from mobiflow_agent.memory.catalog import MemoryCasePersistenceService
from mobiflow_agent.memory.quality import (
    MemoryCaseCatalogQualityReport,
    MemoryCaseNormalizationPreview,
    MemoryCaseQualityAssessment,
    MemoryCaseQualityDecision,
    MemoryCaseQualityPolicy,
    MemoryCaseQualitySchemaVersion,
)
from mobiflow_agent.memory.quality import MemoryCaseQualityService
from mobiflow_agent.memory.case import MemoryCaseRetrievalService
from mobiflow_agent.execution.followup.decisions import RecoveryFollowupDriverDecision
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


def _eval_case(
    replay_case: RecoveryReplayCase,
    *,
    case_id: str = "eval:test",
    category: str = "followup",
    input_summary: str = "eval summary",
) -> RecoveryEvalCase:
    return RecoveryEvalCase(
        case_id=case_id,
        category=category,
        input_summary=input_summary,
        expected_decision=replay_case.harness_response.decision,
        expected_verdict_status=MemoryCaseRetrievalService._extract_verdict_status(replay_case.harness_response),
        replay_case=replay_case,
    )


def _memory_case(
    *,
    case_id: str,
    source: str = "catalog",
    category: str = "followup",
    action_name: str = "create_run",
    decision: RecoveryFollowupDriverDecision = RecoveryFollowupDriverDecision.COMPLETE,
    verdict_status: VerificationStatus | None = VerificationStatus.VERIFIED_SUCCESS,
    input_summary: str | None = None,
    tags: list[str] | None = None,
    with_eval_case: bool = False,
) -> RecoveryMemoryCase:
    replay_case = _replay_case(
        case_id=f"replay:{case_id}",
        action_name=action_name,
        decision=decision,
        verdict_status=verdict_status,
    )
    eval_case = _eval_case(replay_case, case_id=f"eval:{case_id}", category=category) if with_eval_case else None
    case = MemoryCaseRetrievalService().build_case(
        source=source,
        replay_case=replay_case,
        eval_case=eval_case,
        category=category,
        input_summary=input_summary or f"{case_id} summary",
        tags=tags,
    )
    return case.model_copy(update={"case_id": case_id})


def _test_dir(artifact_tmp_path: Path, name: str) -> Path:
    return artifact_dir(artifact_tmp_path, name)


def _save_cases(catalog_dir: Path, cases: list[RecoveryMemoryCase]) -> None:
    persistence = MemoryCasePersistenceService()
    for case in cases:
        persistence.save_to_catalog(case=case, catalog_dir=str(catalog_dir))


def test_assess_clean_case_returns_passed() -> None:
    case = _memory_case(case_id="memory:passed", tags=["device", "verified"], with_eval_case=True)

    result = MemoryCaseQualityService().assess_case(case)

    assert result.decision == MemoryCaseQualityDecision.PASSED
    assert result.issue_count == 0
    assert result.issues == []
    assert "passed quality assessment" in result.summary


def test_preview_normalization_detects_trim_and_tag_cleanup_without_mutating_case() -> None:
    case = _memory_case(
        case_id="memory:normalize",
        source="  catalog  ",
        category=" followup ",
        action_name=" create_run ",
        input_summary="  compact summary  ",
        tags=[" priority ", "", "priority", "device "],
    ).model_copy(update={"tags": [" priority ", "", "priority", "device "]})

    preview = MemoryCaseQualityService().preview_normalization(case)

    assert isinstance(preview, MemoryCaseNormalizationPreview)
    assert preview.normalized_source == "catalog"
    assert preview.normalized_category == "followup"
    assert preview.normalized_action_name == "create_run"
    assert preview.normalized_input_summary == "compact summary"
    assert preview.normalized_tags == ["priority", "device"]
    assert preview.changed_fields == ["source", "category", "action_name", "input_summary", "tags"]
    assert case.source == "  catalog  "
    assert case.tags == [" priority ", "", "priority", "device "]


def test_assess_case_warnings_default_to_warning() -> None:
    case = _memory_case(
        case_id="memory:warning",
        input_summary=" short ",
        tags=["priority", "priority", " "],
    ).model_copy(update={"tags": ["priority", "priority", " "]})

    result = MemoryCaseQualityService().assess_case(case)

    assert result.decision == MemoryCaseQualityDecision.WARNING
    assert result.issue_count == 3
    assert {issue.code for issue in result.issues} == {
        "input_summary_normalized",
        "tags_normalized",
        "input_summary_too_short",
    }


def test_fail_on_warnings_turns_warning_case_into_failed() -> None:
    case = _memory_case(case_id="memory:fail-on-warning", input_summary="short")

    result = MemoryCaseQualityService().assess_case(
        case,
        policy=MemoryCaseQualityPolicy(fail_on_warnings=True),
    )

    assert result.decision == MemoryCaseQualityDecision.FAILED
    assert result.issue_count == 1
    assert result.issues[0].code == "input_summary_too_short"


def test_require_tags_adds_warning_when_catalog_case_has_no_tags() -> None:
    case = _memory_case(case_id="memory:no-tags", tags=[])

    result = MemoryCaseQualityService().assess_case(
        case,
        policy=MemoryCaseQualityPolicy(require_tags=True),
    )

    assert result.decision == MemoryCaseQualityDecision.WARNING
    assert {issue.code for issue in result.issues} == {"tags_required"}


def test_too_many_tags_adds_warning() -> None:
    case = _memory_case(
        case_id="memory:many-tags",
        tags=[f"tag-{index}" for index in range(4)],
    )

    result = MemoryCaseQualityService().assess_case(
        case,
        policy=MemoryCaseQualityPolicy(max_tags=3),
    )

    assert result.decision == MemoryCaseQualityDecision.WARNING
    assert {issue.code for issue in result.issues} == {"too_many_tags"}


def test_consistency_mismatches_fail_assessment() -> None:
    case = _memory_case(case_id="memory:failed", with_eval_case=True)
    mismatched_eval = _eval_case(_replay_case(case_id="replay:other"), case_id="eval:other")
    broken_case = case.model_copy(
        update={
            "action_name": "cancel_run",
            "decision": RecoveryFollowupDriverDecision.HANDOFF_ONLY,
            "verdict_status": VerificationStatus.VERIFIED_FAILED,
            "eval_case": mismatched_eval,
        }
    )

    result = MemoryCaseQualityService().assess_case(broken_case)

    assert result.decision == MemoryCaseQualityDecision.FAILED
    assert {issue.code for issue in result.issues} == {
        "action_name_mismatch",
        "decision_mismatch",
        "verdict_status_mismatch",
        "eval_replay_case_mismatch",
    }


def test_assess_catalog_aggregates_passed_warning_and_failed(artifact_tmp_path) -> None:
    catalog_dir = _test_dir(artifact_tmp_path, "catalog")
    passed_case = _memory_case(case_id="memory:passed", tags=["stable"], with_eval_case=True)
    warning_case = _memory_case(case_id="memory:warning", input_summary="short")
    failed_case = _memory_case(case_id="memory:failed").model_copy(update={"action_name": "cancel_run"})
    _save_cases(catalog_dir, [failed_case, warning_case, passed_case])

    report = MemoryCaseQualityService().assess_catalog(str(catalog_dir))

    assert isinstance(report, MemoryCaseCatalogQualityReport)
    assert report.overall_decision == MemoryCaseQualityDecision.FAILED
    assert report.evaluated_cases == 3
    assert report.passed_cases == 1
    assert report.warning_cases == 1
    assert report.failed_cases == 1
    assert [entry.case_id for entry in report.entries] == [
        "memory:failed",
        "memory:passed",
        "memory:warning",
    ]


def test_empty_catalog_returns_failed_report_with_no_evidence_summary(artifact_tmp_path) -> None:
    catalog_dir = _test_dir(artifact_tmp_path, "empty")

    report = MemoryCaseQualityService().assess_catalog(str(catalog_dir))

    assert report.overall_decision == MemoryCaseQualityDecision.FAILED
    assert report.entries == []
    assert report.issues == []
    assert "no memory evidence" in report.summary


def test_assets_support_roundtrip() -> None:
    case = _memory_case(case_id="memory:roundtrip", tags=["stable"])
    assessment = MemoryCaseQualityService().assess_case(
        case,
        policy=MemoryCaseQualityPolicy(require_tags=True),
    )
    report = MemoryCaseCatalogQualityReport(
        catalog_dir="catalog",
        overall_decision=MemoryCaseQualityDecision.PASSED,
        evaluated_cases=1,
        passed_cases=1,
        warning_cases=0,
        failed_cases=0,
        entries=[],
        issues=[],
        summary="roundtrip",
    )

    restored_assessment = MemoryCaseQualityAssessment.model_validate(
        assessment.model_dump(mode="python")
    )
    restored_report = MemoryCaseCatalogQualityReport.model_validate(report.model_dump(mode="python"))

    assert restored_assessment.schema_version == MemoryCaseQualitySchemaVersion.V1
    assert restored_assessment.case_id == "memory:roundtrip"
    assert restored_assessment.normalization_preview.case_id == "memory:roundtrip"
    assert restored_report.schema_version == MemoryCaseQualitySchemaVersion.V1
    assert restored_report.evaluated_cases == 1


def test_invalid_memory_document_error_is_owned_by_persistence_layer(artifact_tmp_path) -> None:
    catalog_dir = _test_dir(artifact_tmp_path, "invalid")
    (catalog_dir / "broken.json").write_text(
        json.dumps({"schema_version": "v1", "case": {"oops": True}}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Invalid memory case document schema"):
        MemoryCaseQualityService().assess_catalog(str(catalog_dir))


def test_quality_service_stays_static_and_catalog_bound(artifact_tmp_path) -> None:
    catalog_dir = _test_dir(artifact_tmp_path, "static")
    case = _memory_case(case_id="memory:static", tags=["stable"], with_eval_case=True)
    _save_cases(catalog_dir, [case])

    assessment = MemoryCaseQualityService().assess_case(case)
    report = MemoryCaseQualityService().assess_catalog(str(catalog_dir))

    assert assessment.decision == MemoryCaseQualityDecision.PASSED
    assert report.entries[0].case_id == "memory:static"
    assert report.entries[0].issue_count == 0
    assert case.replay_case.case_id == "replay:memory:static"


