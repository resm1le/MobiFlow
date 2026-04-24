from __future__ import annotations

import pytest

from mobiflow_agent.execution.recovery.triage import FailureTriageGuidanceService
from mobiflow_agent.platform.adapter import FakePlatformAdapter, PlatformAdapterError
from mobiflow_agent.platform.types import (
    AttemptContext,
    FailureCategory,
    FailureTriageRecord,
    FailureTriageValidation,
    RecoveryGuidance,
    RetryRecommendation,
    RunTargetContext,
    SuggestedNextAction,
)


def _attempt_context(*, run_id: str = "run-1") -> AttemptContext:
    return AttemptContext(
        attempt_id="attempt-1",
        task_id="task-1",
        device_id="device-1",
        run_id=run_id,
        status="FAILED",
        final_state="FAILED",
        failure_reason="ui_not_found",
    )


def _run_target_context(
    *,
    latest_attempt: AttemptContext | None,
    latest_attempt_id: str | None = "attempt-1",
) -> RunTargetContext:
    return RunTargetContext(
        run_target_id="rt-1",
        device_id="device-1",
        status="FAILED",
        attempt_count=2,
        current_task_id="task-1",
        latest_attempt_id=latest_attempt_id,
        failure_reason="ui_not_found",
        latest_attempt=latest_attempt,
    )


def _triage_record() -> FailureTriageRecord:
    return FailureTriageRecord(
        triage_result_id="triage-1",
        run_target_id="rt-1",
        failure_category=FailureCategory.UI_NOT_FOUND,
        probable_cause="Login button was not visible.",
        confidence=0.87,
        retry_recommendation=RetryRecommendation.INSPECT_PROFILE,
        suggested_next_action=SuggestedNextAction.INSPECT_ARTIFACTS,
        operator_review_hints=["Check the latest screenshot."],
        evidence=["artifact:shot-1"],
        validation=FailureTriageValidation(valid=True, errors=[], warnings=[]),
        model_meta={"provider": "test"},
        generated_at=1710000000000,
    )


def _guidance(*, recommended_action: str = "cancel_run", requires_approval: bool = True) -> RecoveryGuidance:
    return RecoveryGuidance(
        entity_kind="run",
        entity_id="run-1",
        allowed_actions=["cancel_run", "continue_observe"],
        recommended_action=recommended_action,
        requires_approval=requires_approval,
        required_inputs=["runId"],
        prerequisites=["runId"],
        stop_conditions=["confirmation_pending"],
        stop_conditions_summary="Stop when confirmation is pending.",
        why_not_others="Other options do not clear the current blocker.",
        explanation="The run is terminally blocked and should be cancelled.",
        confidence=0.88,
    )


def test_analyze_uses_latest_attempt_run_id_directly() -> None:
    service = FailureTriageGuidanceService(
        FakePlatformAdapter(
            run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context(run_id="run-1"))},
            generated_failure_triage=[_triage_record()],
            recovery_guidance={"run-1": _guidance()},
        )
    )

    response = service.analyze("rt-1")

    assert response.run_target_id == "rt-1"
    assert response.run_id == "run-1"
    assert response.triage.failure_category == FailureCategory.UI_NOT_FOUND
    assert response.recovery_guidance.requires_approval is True
    assert "cancel_run" in response.summary
    assert "approval required" in response.summary


def test_analyze_falls_back_to_get_attempt_when_latest_attempt_lacks_run_id() -> None:
    latest_attempt = _attempt_context(run_id="run-1").model_copy(update={"run_id": "run-2"})
    run_target = _run_target_context(latest_attempt=latest_attempt.model_copy(update={"run_id": ""}))
    service = FailureTriageGuidanceService(
        FakePlatformAdapter(
            run_targets={"rt-1": run_target},
            attempts={"attempt-1": _attempt_context(run_id="run-2")},
            generated_failure_triage=[_triage_record()],
            recovery_guidance={"run-2": _guidance(recommended_action="continue_observe", requires_approval=False)},
        )
    )

    response = service.analyze("rt-1")

    assert response.run_id == "run-2"
    assert response.recovery_guidance.recommended_action == "continue_observe"
    assert "no approval required" in response.summary


def test_get_latest_uses_latest_triage_without_generate() -> None:
    service = FailureTriageGuidanceService(
        FakePlatformAdapter(
            run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context())},
            latest_failure_triage={"rt-1": _triage_record()},
            recovery_guidance={"run-1": _guidance()},
        )
    )

    response = service.get_latest("rt-1")

    assert response.triage.triage_result_id == "triage-1"
    assert response.run_id == "run-1"


def test_guidance_preserves_governed_action_metadata() -> None:
    service = FailureTriageGuidanceService(
        FakePlatformAdapter(
            run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context())},
            latest_failure_triage={"rt-1": _triage_record()},
            recovery_guidance={"run-1": _guidance()},
        )
    )

    response = service.get_latest("rt-1")

    assert response.recovery_guidance.allowed_actions == ["cancel_run", "continue_observe"]
    assert response.recovery_guidance.requires_approval is True


def test_analyze_raises_when_run_id_cannot_be_resolved() -> None:
    service = FailureTriageGuidanceService(
        FakePlatformAdapter(
            run_targets={"rt-1": _run_target_context(latest_attempt=None, latest_attempt_id=None)}
        )
    )

    with pytest.raises(ValueError, match="Could not resolve run_id"):
        service.analyze("rt-1")


def test_analyze_propagates_platform_adapter_error() -> None:
    class BrokenTriageAdapter(FakePlatformAdapter):
        def generate_failure_triage(self, run_target_id: str) -> FailureTriageRecord:
            raise PlatformAdapterError("AI_FAILURE_TRIAGE_NOT_ALLOWED", "Failure triage is not allowed.")

    service = FailureTriageGuidanceService(
        BrokenTriageAdapter(
            run_targets={"rt-1": _run_target_context(latest_attempt=_attempt_context())},
            recovery_guidance={"run-1": _guidance()},
        )
    )

    with pytest.raises(PlatformAdapterError, match="Failure triage is not allowed"):
        service.analyze("rt-1")


