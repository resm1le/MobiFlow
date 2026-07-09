from __future__ import annotations

"""Replay and eval assets and service."""

from enum import Enum
from uuid import uuid4

from pydantic import Field, field_validator

from mobiflow_agent.common.contracts import StrictModel, VerificationStatus
from mobiflow_agent.execution.followup.decisions import RecoveryFollowupDriverDecision
from mobiflow_agent.execution.recovery.governed.models import GovernedRecoveryExecutionResponse
from mobiflow_agent.runtime.harness import TaskHarnessResponse

class ReplayEvalSchemaVersion(str, Enum):
    V1 = "v1"

class RecoveryReplayCase(StrictModel):
    schema_version: ReplayEvalSchemaVersion = ReplayEvalSchemaVersion.V1
    case_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    execution: GovernedRecoveryExecutionResponse
    harness_response: TaskHarnessResponse

    @field_validator("harness_response", mode="before")
    @classmethod
    def validate_harness_response(cls, value):
        return TaskHarnessResponse.model_validate(value)

class RecoveryEvalCase(StrictModel):
    schema_version: ReplayEvalSchemaVersion = ReplayEvalSchemaVersion.V1
    case_id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    input_summary: str = Field(min_length=1)
    expected_decision: RecoveryFollowupDriverDecision | None = None
    expected_verdict_status: VerificationStatus | None = None
    replay_case: RecoveryReplayCase

class RecoveryEvalResult(StrictModel):
    schema_version: ReplayEvalSchemaVersion = ReplayEvalSchemaVersion.V1
    case_id: str = Field(min_length=1)
    matched: bool
    actual_decision: RecoveryFollowupDriverDecision
    actual_verdict_status: VerificationStatus | None = None
    summary: str = Field(min_length=1)

def build_replay_case_id() -> str:
    return f"replay:{uuid4().hex}"

def build_eval_case_id() -> str:
    return f"eval:{uuid4().hex}"


class ReplayEvalService:
    def build_replay_case(
        self,
        *,
        source: str,
        execution: GovernedRecoveryExecutionResponse,
        harness_response,
    ) -> RecoveryReplayCase:
        return RecoveryReplayCase(
            case_id=build_replay_case_id(),
            source=source,
            execution=execution,
            harness_response=TaskHarnessResponse.model_validate(harness_response),
        )

    def build_eval_case(
        self,
        *,
        category: str,
        input_summary: str,
        execution: GovernedRecoveryExecutionResponse,
        harness_response,
        expected_decision: RecoveryFollowupDriverDecision | None = None,
        expected_verdict_status: VerificationStatus | None = None,
    ) -> RecoveryEvalCase:
        replay_case = self.build_replay_case(
            source=category,
            execution=execution,
            harness_response=harness_response,
        )
        return RecoveryEvalCase(
            case_id=build_eval_case_id(),
            category=category,
            input_summary=input_summary,
            expected_decision=expected_decision,
            expected_verdict_status=expected_verdict_status,
            replay_case=replay_case,
        )

    def evaluate(self, case: RecoveryEvalCase) -> RecoveryEvalResult:
        actual_decision = case.replay_case.harness_response.decision
        actual_verdict_status = self._extract_verdict_status(case.replay_case.harness_response)
        mismatches: list[str] = []

        if case.expected_decision is not None and actual_decision != case.expected_decision:
            actual_text = actual_decision.value if actual_decision is not None else "none"
            mismatches.append(
                f"decision expected {case.expected_decision.value} but got {actual_text}"
            )
        if case.expected_verdict_status is not None and actual_verdict_status != case.expected_verdict_status:
            actual_text = actual_verdict_status.value if actual_verdict_status is not None else "none"
            mismatches.append(
                f"verdict expected {case.expected_verdict_status.value} but got {actual_text}"
            )

        matched = not mismatches
        summary = (
            "Replay/eval case matched expected fields."
            if matched
            else "Replay/eval case mismatched: " + "; ".join(mismatches)
        )
        return RecoveryEvalResult(
            case_id=case.case_id,
            matched=matched,
            actual_decision=actual_decision,
            actual_verdict_status=actual_verdict_status,
            summary=summary,
        )

    @staticmethod
    def _extract_verdict_status(
        harness_response: TaskHarnessResponse,
    ) -> VerificationStatus | None:
        if harness_response.latest_verdict is None:
            return None
        return harness_response.latest_verdict.status
