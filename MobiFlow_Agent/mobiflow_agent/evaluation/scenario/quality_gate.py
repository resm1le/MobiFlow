from __future__ import annotations

from mobiflow_agent.common.contracts import EvidenceRef, VerificationStatus
from mobiflow_agent.evaluation.scenario.models import ScenarioEvaluationCase, ScenarioEvaluationResult
from mobiflow_agent.runtime.harness import TaskHarnessStatus


class ScenarioQualityGate:
    def evaluate(
        self,
        case: ScenarioEvaluationCase,
        result: ScenarioEvaluationResult,
    ) -> ScenarioEvaluationResult:
        failures: list[str] = []
        expectation = case.expectation
        final_response = result.final_response

        if expectation.expected_final_status is not None and final_response.status != expectation.expected_final_status:
            failures.append(
                f"final status expected {expectation.expected_final_status.value} but got {final_response.status.value}"
            )
        actual_verification_status = (
            final_response.latest_verdict.status if final_response.latest_verdict is not None else None
        )
        if (
            expectation.expected_verification_status is not None
            and actual_verification_status != expectation.expected_verification_status
        ):
            actual = actual_verification_status.value if actual_verification_status is not None else "none"
            failures.append(
                f"verification status expected {expectation.expected_verification_status.value} but got {actual}"
            )

        evidence_refs = self._collect_evidence(result)
        evidence_ids = {evidence.evidence_id for evidence in evidence_refs}
        evidence_kinds = {evidence.kind for evidence in evidence_refs}
        for evidence_id in expectation.required_evidence_ids:
            if evidence_id not in evidence_ids:
                failures.append(f"required evidence id missing: {evidence_id}")
        for evidence_kind in expectation.required_evidence_kinds:
            if evidence_kind not in evidence_kinds:
                failures.append(f"required evidence kind missing: {evidence_kind.value}")

        action_names = [trace.action_tool_name for trace in result.action_traces]
        for action_name in expectation.required_actions:
            if action_name not in action_names:
                failures.append(f"required action missing: {action_name}")
        for action_name in expectation.forbidden_actions:
            if action_name in action_names:
                failures.append(f"forbidden action observed: {action_name}")

        approval_pause_observed = any(
            response.status == TaskHarnessStatus.AWAITING_APPROVAL for response in result.responses
        )
        if expectation.expect_approval_pause and not approval_pause_observed:
            failures.append("expected approval pause was not observed")
        if not expectation.expect_approval_pause and approval_pause_observed:
            failures.append("unexpected approval pause was observed")

        if expectation.expect_recovery_path and not self._recovery_path_observed(result):
            failures.append("expected recovery path was not observable from harness responses")

        matched = not failures
        summary = (
            f"Scenario {case.name} matched all expectations."
            if matched
            else f"Scenario {case.name} failed quality gate: " + "; ".join(failures)
        )
        return result.model_copy(update={"matched": matched, "failures": failures, "summary": summary})

    @staticmethod
    def _collect_evidence(result: ScenarioEvaluationResult) -> list[EvidenceRef]:
        refs: list[EvidenceRef] = []
        for response in result.responses:
            if response.latest_verdict is None:
                continue
            refs.extend(response.latest_verdict.evidence_refs)
        return refs

    @staticmethod
    def _recovery_path_observed(result: ScenarioEvaluationResult) -> bool:
        for response in result.responses:
            if response.context_handoff is not None:
                return True
            if response.runtime_state is not None:
                if response.runtime_state.recovery_summary:
                    return True
                if response.runtime_state.recovery_execution is not None:
                    return True
                if response.runtime_state.recovery_observation is not None:
                    return True
            if response.latest_verdict is None:
                continue
            if response.latest_verdict.status in {
                VerificationStatus.BLOCKED,
                VerificationStatus.VERIFIED_FAILED,
                VerificationStatus.VERIFIED_UNKNOWN,
            }:
                return True
        return False


__all__ = ["ScenarioQualityGate"]
