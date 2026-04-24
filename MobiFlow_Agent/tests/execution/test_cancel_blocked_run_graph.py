from __future__ import annotations

from mobiflow_agent.execution.recovery.blocked_run import (
    build_cancel_blocked_run_graph,
    build_initial_cancel_run_state,
    resume_cancel_blocked_run,
)
from mobiflow_agent.common.contracts import VerificationStatus
from mobiflow_agent.platform.evidence import build_run_observation_view
from mobiflow_agent.platform.adapter import FakePlatformAdapter
from mobiflow_agent.platform.types import (
    GovernedActionResult,
    GovernedActionState,
    PlatformEntityRefs,
    ToolAuditRef,
    ToolExecutionError,
    ToolRiskLevel,
)
from mobiflow_agent.runtime.state import AgentRuntimeState, RuntimeLifecycle


def _tool_audit(audit_id: str) -> ToolAuditRef:
    return ToolAuditRef(audit_id=audit_id, risk_level=ToolRiskLevel.EXECUTION)


def _governed_result(
    *,
    state: GovernedActionState,
    proposal_id: str = "proposal-1",
    confirmation_id: str | None = None,
    confirmation_summary: str | None = None,
    error: ToolExecutionError | None = None,
    audit_id: str = "audit-1",
) -> GovernedActionResult:
    return GovernedActionResult(
        state=state,
        proposal_id=proposal_id,
        action_tool_name="cancel_run",
        audit=_tool_audit(audit_id),
        entity_refs=PlatformEntityRefs(proposal_id=proposal_id, run_id="run-1"),
        confirmation_id=confirmation_id,
        confirmation_summary=confirmation_summary,
        confirmation_expires_at=1710000000000 if confirmation_id else None,
        result={"status": "ok"} if state != GovernedActionState.FAILED else {},
        error=error,
    )


def _run_observation(
    *,
    status: str | None,
    allow_cancel: bool,
    include_diagnosis: bool = True,
) -> object:
    governance_result = {
        "runId": "run-1",
        "status": status,
        "blockers": [{"code": "executor_stalled"}] if status == "BLOCKED" else [],
        "latestAttemptIds": ["attempt-1"] if include_diagnosis else [],
        "lastUpdatedAt": 1710000000100,
    }
    lineage_result = {
        "runId": "run-1",
        "currentGovernedOptions": ["cancel_run"] if allow_cancel else [],
        "latestArtifacts": [],
    }
    diagnosis_response = (
        {
            "status": "completed",
            "result": {
                "attemptId": "attempt-1",
                "keyEvents": [{"eventType": "STALL", "message": "Executor stalled"}],
                "failureSignals": [{"code": "stalled"}],
            },
        }
        if include_diagnosis
        else None
    )
    return build_run_observation_view(
        run_id="run-1",
        governance_response={"status": "completed", "result": governance_result},
        lineage_response={"status": "completed", "result": lineage_result},
        diagnosis_response=diagnosis_response,
    )


def _state(result: dict) -> AgentRuntimeState:
    return AgentRuntimeState.model_validate(result)


def test_cancel_blocked_run_graph_approval_success() -> None:
    adapter = FakePlatformAdapter(
        run_observations={
            "run-1": [
                _run_observation(status="BLOCKED", allow_cancel=True),
                _run_observation(status="CANCELLED", allow_cancel=False, include_diagnosis=False),
            ]
        },
        submit_results=[
            _governed_result(
                state=GovernedActionState.APPROVAL_REQUIRED,
                confirmation_id="confirm-1",
                confirmation_summary="Approve cancelling run-1",
            )
        ],
        resolve_results=[_governed_result(state=GovernedActionState.EXECUTED, audit_id="audit-2")],
    )
    app = build_cancel_blocked_run_graph(adapter)
    config = {"configurable": {"thread_id": "approval-success"}}

    app.invoke(build_initial_cancel_run_state("run-1").model_dump(mode="python"), config=config)
    paused = app.get_state(config).values
    paused_state = _state(paused)

    assert paused_state.lifecycle == RuntimeLifecycle.AWAITING_APPROVAL
    assert paused_state.pending_execution is not None
    assert paused_state.pending_execution.confirmation_state.value == "required"

    final = _state(resume_cancel_blocked_run(app, config, paused, approved=True))

    assert final.lifecycle == RuntimeLifecycle.COMPLETED
    assert final.latest_verdict is not None
    assert final.latest_verdict.status == VerificationStatus.VERIFIED_SUCCESS


def test_cancel_blocked_run_graph_approval_rejected_blocks() -> None:
    adapter = FakePlatformAdapter(
        run_observations={"run-1": [_run_observation(status="BLOCKED", allow_cancel=True)]},
        submit_results=[
            _governed_result(
                state=GovernedActionState.APPROVAL_REQUIRED,
                confirmation_id="confirm-1",
                confirmation_summary="Approve cancelling run-1",
            )
        ],
        resolve_results=[
            _governed_result(
                state=GovernedActionState.FAILED,
                audit_id="audit-2",
                error=ToolExecutionError(code="CONFIRMATION_REJECTED", message="User rejected confirmation."),
            )
        ],
    )
    app = build_cancel_blocked_run_graph(adapter)
    config = {"configurable": {"thread_id": "approval-rejected"}}

    app.invoke(build_initial_cancel_run_state("run-1").model_dump(mode="python"), config=config)
    paused = app.get_state(config).values
    final = _state(resume_cancel_blocked_run(app, config, paused, approved=False))

    assert final.lifecycle == RuntimeLifecycle.BLOCKED
    assert final.latest_verdict is not None
    assert final.latest_verdict.status == VerificationStatus.BLOCKED
    assert final.latest_verdict.blocked_reason == "approval_rejected"


def test_cancel_blocked_run_graph_run_not_cancellable_blocks() -> None:
    adapter = FakePlatformAdapter(
        run_observations={"run-1": _run_observation(status="BLOCKED", allow_cancel=False)}
    )
    app = build_cancel_blocked_run_graph(adapter)
    config = {"configurable": {"thread_id": "not-cancellable"}}

    final = _state(app.invoke(build_initial_cancel_run_state("run-1").model_dump(mode="python"), config=config))

    assert final.lifecycle == RuntimeLifecycle.BLOCKED
    assert final.latest_verdict is not None
    assert final.latest_verdict.status == VerificationStatus.BLOCKED
    assert final.latest_verdict.blocked_reason == "cancel_run_not_allowed"


def test_cancel_blocked_run_graph_completed_but_not_cancelled_is_verified_failed() -> None:
    adapter = FakePlatformAdapter(
        run_observations={
            "run-1": [
                _run_observation(status="BLOCKED", allow_cancel=True),
                _run_observation(status="FAILED", allow_cancel=False, include_diagnosis=False),
            ]
        },
        submit_results=[_governed_result(state=GovernedActionState.EXECUTED)],
    )
    app = build_cancel_blocked_run_graph(adapter)
    config = {"configurable": {"thread_id": "verified-failed"}}

    final = _state(app.invoke(build_initial_cancel_run_state("run-1").model_dump(mode="python"), config=config))

    assert final.lifecycle == RuntimeLifecycle.COMPLETED
    assert final.latest_verdict is not None
    assert final.latest_verdict.status == VerificationStatus.VERIFIED_FAILED


def test_cancel_blocked_run_graph_completed_but_unprovable_is_verified_unknown() -> None:
    adapter = FakePlatformAdapter(
        run_observations={
            "run-1": [
                _run_observation(status="BLOCKED", allow_cancel=True),
                _run_observation(status=None, allow_cancel=False, include_diagnosis=False),
            ]
        },
        submit_results=[_governed_result(state=GovernedActionState.EXECUTED)],
    )
    app = build_cancel_blocked_run_graph(adapter)
    config = {"configurable": {"thread_id": "verified-unknown"}}

    final = _state(app.invoke(build_initial_cancel_run_state("run-1").model_dump(mode="python"), config=config))

    assert final.lifecycle == RuntimeLifecycle.COMPLETED
    assert final.latest_verdict is not None
    assert final.latest_verdict.status == VerificationStatus.VERIFIED_UNKNOWN



