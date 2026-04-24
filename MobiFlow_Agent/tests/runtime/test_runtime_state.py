import pytest
from pydantic import ValidationError

from mobiflow_agent.common.contracts import (
    EntityKind,
    ExecutionProposal,
    ObservationView,
    SuccessCriterion,
    TaskContract,
    VerificationCheck,
    VerificationSpec,
)
from mobiflow_agent.platform.types import (
    GovernedActionResult,
    GovernedActionState,
    PlatformEntityRefs,
    RunAttemptCounts,
    RunCounts,
    RunGovernanceSnapshot,
    ToolCatalogItem,
    ToolAuditRef,
    ToolRiskLevel,
)
from mobiflow_agent.execution.recovery.execution import RecoveryExecutionContext, RecoveryObservationResult
from mobiflow_agent.runtime.state import (
    AgentRuntimeState,
    CallerContext,
    ConfirmationState,
    PendingExecution,
    RuntimeLifecycle,
)


def build_contract() -> TaskContract:
    return TaskContract(
        contract_id="contract-1",
        user_goal="Cancel blocked run.",
        outcome="Run enters cancelled state.",
        target_kind=EntityKind.RUN,
        target_id="run-1",
        success_criteria=[
            SuccessCriterion(
                criterion_id="criterion-1",
                description="Run status becomes CANCELLED.",
            )
        ],
    )


def build_proposal() -> ExecutionProposal:
    return ExecutionProposal(
        proposal_id="proposal-1",
        action_tool_name="cancel_run",
        arguments={"runId": "run-1"},
        target_kind=EntityKind.RUN,
        target_id="run-1",
        rationale="Blocked run should be cancelled.",
    )


def build_verification() -> VerificationSpec:
    return VerificationSpec(
        verification_id="verification-1",
        target_kind=EntityKind.RUN,
        target_id="run-1",
        success_checks=[
            VerificationCheck(
                check_id="check-1",
                description="Run status is CANCELLED.",
            )
        ],
    )


def test_runtime_state_requires_pending_execution_when_awaiting_approval() -> None:
    with pytest.raises(ValidationError):
        AgentRuntimeState(
            session_id="session-1",
            lifecycle=RuntimeLifecycle.AWAITING_APPROVAL,
        )


def test_runtime_state_requires_verification_spec_when_verifying() -> None:
    with pytest.raises(ValidationError):
        AgentRuntimeState(
            session_id="session-1",
            lifecycle=RuntimeLifecycle.VERIFYING,
        )


def test_runtime_state_can_hold_main_loop_objects() -> None:
    state = AgentRuntimeState(
        session_id="session-1",
        lifecycle=RuntimeLifecycle.AWAITING_APPROVAL,
        turn_index=1,
        step_index=2,
        active_contract=build_contract(),
        focus_kind=EntityKind.RUN,
        focus_id="run-1",
        latest_observation=ObservationView(
            observation_id="obs-1",
            focus_kind=EntityKind.RUN,
            focus_id="run-1",
        ),
        pending_execution=PendingExecution(
            proposal=build_proposal(),
            caller_context=CallerContext(
                session_id="session-1",
                agent_task_id="task-1",
                turn_id="turn-1",
                step_id="step-2",
            ),
            confirmation_state=ConfirmationState.REQUIRED,
            confirmation_id="confirm-1",
            confirmation_summary="Cancel blocked run",
            confirmation_expires_at=1710000000000,
            audit=ToolAuditRef(audit_id="audit-1", risk_level=ToolRiskLevel.EXECUTION),
            entity_refs=PlatformEntityRefs(proposal_id="proposal-1", run_id="run-1"),
        ),
        active_verification=build_verification(),
    )

    assert state.pending_execution is not None
    assert state.pending_execution.proposal.action_tool_name == "cancel_run"
    assert state.pending_execution.audit is not None
    assert state.pending_execution.entity_refs is not None


def test_runtime_state_can_hold_recovery_execution_context() -> None:
    state = AgentRuntimeState(
        session_id="session-1",
        lifecycle=RuntimeLifecycle.VERIFYING,
        focus_kind=EntityKind.RUN_TARGET,
        focus_id="rt-1",
        recovery_execution=RecoveryExecutionContext(
            run_target_id="rt-1",
            source_run_id="run-1",
            action_name="create_run",
            recommended_action="create_run",
            proposal_id="proposal-1",
            created_run_id="run-created",
        ),
        recovery_observation=RecoveryObservationResult(
            created_governance=RunGovernanceSnapshot(
                run_id="run-created",
                status="QUEUED",
                target_counts=RunCounts(
                    total_targets=1,
                    queued=1,
                    running=0,
                    retry_pending=0,
                    succeeded=0,
                    failed=0,
                    cancelled=0,
                ),
                attempt_counts=RunAttemptCounts(total=0, running=0, failed=0, succeeded=0),
                latest_attempt_ids=[],
                blockers=[],
                last_updated_at=1710000000000,
            )
        ),
        active_verification=build_verification(),
    )

    assert state.recovery_execution is not None
    assert state.recovery_execution.created_run_id == "run-created"
    assert state.recovery_observation is not None


def test_platform_adapter_shapes_are_instantiable() -> None:
    item = ToolCatalogItem(
        name="cancel_run",
        tool_kind="tool",
        risk_level=ToolRiskLevel.EXECUTION,
        requires_approval=True,
        semantic_tags=["run", "governance"],
    )
    result = GovernedActionResult(
        state=GovernedActionState.APPROVAL_REQUIRED,
        proposal_id="proposal-1",
        action_tool_name="cancel_run",
        confirmation_id="confirm-1",
        confirmation_summary="Cancel blocked run",
        audit=ToolAuditRef(audit_id="audit-1", risk_level=ToolRiskLevel.EXECUTION),
        entity_refs=PlatformEntityRefs(proposal_id="proposal-1", run_id="run-1"),
    )

    assert item.requires_approval is True
    assert result.state == GovernedActionState.APPROVAL_REQUIRED


