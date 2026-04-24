from mobiflow_agent.agents.contracts import AgentRole, RoleRequest, RoleResult


def test_role_request_and_result_roundtrip() -> None:
    request = RoleRequest(
        request_id="role-request-1",
        role=AgentRole.PLANNER,
        session_id="task-session-1",
        step_id="step-1",
        reason="Build the initial task plan.",
        payload={"goal": "Cancel the blocked run"},
    )
    result = RoleResult(
        result_id="role-result-1",
        role=AgentRole.PLANNER,
        session_id="task-session-1",
        step_id="step-1",
        summary="Planner returned the initial plan.",
        payload={"plan_id": "plan-1"},
        handoff_reason="plan_ready",
        next_role=AgentRole.OBSERVER,
    )

    restored_request = RoleRequest.model_validate(request.model_dump(mode="python"))
    restored_result = RoleResult.model_validate(result.model_dump(mode="python"))

    assert restored_request.role == AgentRole.PLANNER
    assert restored_request.payload["goal"] == "Cancel the blocked run"
    assert restored_result.role == AgentRole.PLANNER
    assert restored_result.handoff_reason == "plan_ready"
    assert restored_result.next_role == AgentRole.OBSERVER
