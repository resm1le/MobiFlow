import pytest
from pydantic import ValidationError

from mobiflow_agent.common.contracts import (
    EntityKind,
    EvidenceKind,
    EvidenceRef,
    ExecutionProposal,
    ObservationFact,
    ObservationFactSource,
    ObservationInference,
    ObservationView,
    SuccessCriterion,
    TaskContract,
    VerificationCheck,
    VerificationSpec,
    VerificationStatus,
    VerificationVerdict,
)


def build_evidence() -> EvidenceRef:
    return EvidenceRef(
        evidence_id="e-1",
        kind=EvidenceKind.PLATFORM_SNAPSHOT,
        summary="Run governance snapshot after execution.",
        locator="run-governance-snapshot:run-1",
    )


def test_task_contract_requires_success_criteria() -> None:
    with pytest.raises(ValidationError):
        TaskContract(
            contract_id="contract-1",
            user_goal="Cancel the blocked run safely.",
            outcome="Run is cancelled with proof.",
        )


def test_observation_view_allows_inferences_only_from_known_facts() -> None:
    with pytest.raises(ValidationError):
        ObservationView(
            observation_id="obs-1",
            focus_kind=EntityKind.RUN,
            focus_id="run-1",
            facts=[
                ObservationFact(
                    fact_id="fact-1",
                    source=ObservationFactSource.PLATFORM,
                    title="Run status",
                    value={"status": "BLOCKED"},
                    evidence_refs=[build_evidence()],
                )
            ],
            inferences=[
                ObservationInference(
                    inference_id="inf-1",
                    statement="Run is still safe to cancel.",
                    based_on_fact_ids=["fact-missing"],
                    confidence=0.81,
                )
            ],
        )


def test_execution_proposal_rejects_meta_tool() -> None:
    with pytest.raises(ValidationError):
        ExecutionProposal(
            proposal_id="proposal-1",
            action_tool_name="propose_governed_action",
            arguments={"runId": "run-1"},
            rationale="Need to cancel the blocked run.",
        )


def test_verification_spec_requires_checks() -> None:
    with pytest.raises(ValidationError):
        VerificationSpec(
            verification_id="verify-1",
            target_kind=EntityKind.RUN,
            target_id="run-1",
        )


def test_verification_verdict_requires_evidence_for_verified_failure() -> None:
    with pytest.raises(ValidationError):
        VerificationVerdict(
            verdict_id="verdict-1",
            status=VerificationStatus.VERIFIED_FAILED,
            summary="Run did not enter cancelled state.",
            target_kind=EntityKind.RUN,
            target_id="run-1",
            unmatched_check_ids=["check-1"],
        )


def test_happy_path_contracts_can_be_instantiated() -> None:
    contract = TaskContract(
        contract_id="contract-1",
        user_goal="Cancel the blocked run safely.",
        outcome="Run enters cancelled state and no active attempts remain.",
        target_kind=EntityKind.RUN,
        target_id="run-1",
        success_criteria=[
            SuccessCriterion(
                criterion_id="criterion-1",
                description="Run status becomes CANCELLED.",
                evidence_hint="run governance snapshot",
            )
        ],
    )

    observation = ObservationView(
        observation_id="obs-1",
        focus_kind=EntityKind.RUN,
        focus_id="run-1",
        facts=[
            ObservationFact(
                fact_id="fact-1",
                source=ObservationFactSource.PLATFORM,
                title="Run status",
                value={"status": "CANCELLED"},
                evidence_refs=[build_evidence()],
            )
        ],
        inferences=[
            ObservationInference(
                inference_id="inf-1",
                statement="The cancel action reached the expected state.",
                based_on_fact_ids=["fact-1"],
                confidence=0.93,
            )
        ],
    )

    proposal = ExecutionProposal(
        proposal_id="proposal-1",
        action_tool_name="cancel_run",
        arguments={"runId": "run-1"},
        target_kind=EntityKind.RUN,
        target_id="run-1",
        rationale="Run is blocked and current governance state allows cancellation.",
        preconditions={"runId": "run-1", "status": "BLOCKED"},
        expected_observation_changes=["run status becomes CANCELLED"],
        confidence=0.84,
    )

    spec = VerificationSpec(
        verification_id="verify-1",
        target_kind=EntityKind.RUN,
        target_id="run-1",
        success_checks=[
            VerificationCheck(
                check_id="check-1",
                description="Run status is CANCELLED in the latest governance snapshot.",
                evidence_hint="get_run_governance_snapshot",
            )
        ],
    )

    verdict = VerificationVerdict(
        verdict_id="verdict-1",
        status=VerificationStatus.VERIFIED_SUCCESS,
        summary="Run cancellation verified from platform state.",
        target_kind=EntityKind.RUN,
        target_id="run-1",
        matched_check_ids=["check-1"],
        evidence_refs=[build_evidence()],
    )

    assert contract.target_id == "run-1"
    assert observation.facts[0].fact_id == "fact-1"
    assert proposal.action_tool_name == "cancel_run"
    assert spec.success_checks[0].check_id == "check-1"
    assert verdict.status == VerificationStatus.VERIFIED_SUCCESS


