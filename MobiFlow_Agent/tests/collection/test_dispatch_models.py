from __future__ import annotations

import pytest
from pydantic import ValidationError

from mobiflow_agent.collection.models import (
    CollectionDispatchResult,
    CollectionDispatchStatus,
    CollectionIntent,
    DispatchCompilationResult,
    DispatchEntry,
    DispatchPlan,
    ExplicitDeviceSelector,
    IntentPlannerDecision,
    IntentPlannerDecisionType,
    IntentPlanningResult,
    TaggedDeviceSelector,
)
from mobiflow_agent.common.contracts import ExecutionProposal
from mobiflow_agent.platform.types import GovernedActionResult, GovernedActionState


def _plan() -> DispatchPlan:
    return DispatchPlan(
        name="mixed collection",
        dispatch=[
            DispatchEntry(
                sequence_id="wechat.text_chat.v1",
                select=TaggedDeviceSelector(count=2, required_tags=["android13"]),
            )
        ],
    )


def _proposal() -> ExecutionProposal:
    return ExecutionProposal(
        proposal_id="collection-dispatch:session-1:turn-1",
        action_tool_name="create_heterogeneous_run",
        arguments={"name": "mixed collection"},
        rationale="Compile an explicitly requested collection batch.",
        confidence=0.9,
    )


@pytest.mark.parametrize("field", ["raw_text", "task_type"])
def test_collection_intent_rejects_blank_required_text(field: str) -> None:
    values = {"raw_text": "collect text chat", "task_type": "PLUGIN_RUN"}
    values[field] = "   "

    with pytest.raises(ValidationError):
        CollectionIntent(**values)


def test_collection_intent_mutable_labels_are_isolated() -> None:
    first = CollectionIntent(raw_text="first")
    second = CollectionIntent(raw_text="second")

    first.labels.append("pcap")

    assert second.labels == []


def test_explicit_selector_rejects_empty_blank_and_duplicate_ids() -> None:
    for device_ids in ([], [""], ["dev-1", "dev-1"]):
        with pytest.raises(ValidationError):
            ExplicitDeviceSelector(device_ids=device_ids)


def test_tagged_selector_rejects_invalid_count_duplicates_and_overlap() -> None:
    with pytest.raises(ValidationError):
        TaggedDeviceSelector(count=0)
    with pytest.raises(ValidationError):
        TaggedDeviceSelector(count=1, required_tags=["android13", "android13"])
    with pytest.raises(ValidationError):
        TaggedDeviceSelector(
            count=1,
            required_tags=["android13"],
            excluded_tags=["android13"],
        )


def test_dispatch_entry_selector_union_rejects_mixed_or_empty_shape() -> None:
    with pytest.raises(ValidationError):
        DispatchEntry(
            sequence_id="wechat.text_chat.v1",
            select={"count": 1, "device_ids": ["dev-1"]},
        )
    with pytest.raises(ValidationError):
        DispatchEntry(sequence_id="wechat.text_chat.v1", select={})


def test_dispatch_entry_requires_versioned_sequence_id() -> None:
    with pytest.raises(ValidationError):
        DispatchEntry(
            sequence_id="wechat.text_chat",
            select=TaggedDeviceSelector(count=1),
        )


def test_dispatch_plan_requires_nonblank_name_and_nonempty_dispatch() -> None:
    with pytest.raises(ValidationError):
        DispatchPlan(name=" ", dispatch=_plan().dispatch)
    with pytest.raises(ValidationError):
        DispatchPlan(name="empty", dispatch=[])


def test_intent_planner_decision_enforces_plan_or_clarification() -> None:
    with pytest.raises(ValidationError):
        IntentPlannerDecision(
            decision_type=IntentPlannerDecisionType.PLAN,
            confidence=0.8,
        )
    with pytest.raises(ValidationError):
        IntentPlannerDecision(
            decision_type=IntentPlannerDecisionType.CLARIFY,
            confidence=0.2,
        )
    with pytest.raises(ValidationError):
        IntentPlannerDecision(
            decision_type=IntentPlannerDecisionType.CLARIFY,
            plan=_plan(),
            clarification_questions=["Which devices?"],
            confidence=0.2,
        )


def test_intent_planning_result_enforces_status_invariants() -> None:
    with pytest.raises(ValidationError):
        IntentPlanningResult(status=CollectionDispatchStatus.PLANNED)
    with pytest.raises(ValidationError):
        IntentPlanningResult(
            status=CollectionDispatchStatus.NEEDS_CLARIFICATION,
            plan=_plan(),
            clarification_questions=["Which devices?"],
        )

    result = IntentPlanningResult(
        status=CollectionDispatchStatus.NEEDS_CLARIFICATION,
        clarification_questions=["Which devices?"],
    )
    assert result.plan is None


def test_dispatch_compilation_result_enforces_proposal_invariant() -> None:
    with pytest.raises(ValidationError):
        DispatchCompilationResult(accepted=True)
    with pytest.raises(ValidationError):
        DispatchCompilationResult(accepted=False, proposal=_proposal())


def test_collection_dispatch_result_enforces_planned_invariant() -> None:
    with pytest.raises(ValidationError):
        CollectionDispatchResult(
            status=CollectionDispatchStatus.PLANNED,
            plan=_plan(),
        )

    result = CollectionDispatchResult(
        status=CollectionDispatchStatus.PLANNED,
        plan=_plan(),
        proposal=_proposal(),
    )
    assert result.governed_result is None


@pytest.mark.parametrize(
    ("status", "governed_state"),
    [
        (CollectionDispatchStatus.APPROVAL_REQUIRED, GovernedActionState.APPROVAL_REQUIRED),
        (CollectionDispatchStatus.EXECUTED, GovernedActionState.EXECUTED),
        (CollectionDispatchStatus.FAILED, GovernedActionState.FAILED),
    ],
)
def test_collection_dispatch_result_matches_governed_state(
    status: CollectionDispatchStatus,
    governed_state: GovernedActionState,
) -> None:
    governed = GovernedActionResult(
        state=governed_state,
        proposal_id=_proposal().proposal_id,
        action_tool_name="create_heterogeneous_run",
    )
    result = CollectionDispatchResult(
        status=status,
        plan=_plan(),
        proposal=_proposal(),
        governed_result=governed,
    )
    assert result.status == status

    wrong_status = (
        CollectionDispatchStatus.EXECUTED
        if status != CollectionDispatchStatus.EXECUTED
        else CollectionDispatchStatus.FAILED
    )
    with pytest.raises(ValidationError):
        CollectionDispatchResult(
            status=wrong_status,
            plan=_plan(),
            proposal=_proposal(),
            governed_result=governed,
        )


def test_non_submission_results_cannot_carry_proposal_or_governed_result() -> None:
    governed = GovernedActionResult(
        state=GovernedActionState.FAILED,
        proposal_id=_proposal().proposal_id,
        action_tool_name="create_heterogeneous_run",
    )
    for status in (
        CollectionDispatchStatus.NEEDS_CLARIFICATION,
        CollectionDispatchStatus.REJECTED,
        CollectionDispatchStatus.ERROR,
    ):
        with pytest.raises(ValidationError):
            CollectionDispatchResult(
                status=status,
                proposal=_proposal(),
                governed_result=governed,
            )
