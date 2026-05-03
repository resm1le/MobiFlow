from mobiflow_agent.agents import AgentRole
from mobiflow_agent.agents.planner import PlannerAgent
from mobiflow_agent.common.contracts import EntityKind, ExecutionProposal, VerificationCheck, VerificationSpec
from mobiflow_agent.model import ModelProfile, ModelRegistry, ModelRuntime, RoleModelPolicy
from mobiflow_agent.model.providers import NoopModelClient
from mobiflow_agent.task.plan import TaskStepKind
from mobiflow_agent.task.session import TaskSession


def _proposal() -> ExecutionProposal:
    return ExecutionProposal(
        proposal_id="proposal-1",
        action_tool_name="cancel_run",
        arguments={"runId": "run-123"},
        target_kind=EntityKind.RUN,
        target_id="run-123",
        rationale="Cancel the blocked run.",
    )


def _verification_spec() -> VerificationSpec:
    return VerificationSpec(
        verification_id="verification:run:run-123",
        target_kind=EntityKind.RUN,
        target_id="run-123",
        success_checks=[
            VerificationCheck(
                check_id="run-cancelled",
                description="The run reaches cancelled status.",
                evidence_hint="cancelled",
            )
        ],
    )


def test_planner_agent_uses_model_runtime_and_records_trace() -> None:
    runtime = ModelRuntime(
        ModelRegistry(
            profiles=[ModelProfile(name="planner-profile", provider="noop", model="noop-model")],
            clients={
                "noop": NoopModelClient(
                    responses=[
                        {
                            "contract": {
                                "contract_id": "contract-1",
                                "user_goal": "Cancel the blocked run",
                                "outcome": "Cancel the blocked run safely",
                                "target_kind": "run",
                                "target_id": "run-123",
                                "success_criteria": [
                                    {
                                        "criterion_id": "primary",
                                        "description": "Finish with evidence-backed verification.",
                                    }
                                ],
                                "verification_focus": ["evidence", "task-progress"],
                                "approval_mode": "on_risk",
                            },
                            "plan": {
                                "plan_id": "plan-1",
                                "summary": "Cancel blocked run",
                                "steps": [
                                    {
                                        "step_id": "step-1",
                                        "kind": "dynamic",
                                        "goal": "Cancel the run and verify the run state.",
                                        "expected_outputs": ["dynamic_step_outcome"],
                                        "verification_target_kind": "run",
                                        "verification_target_id": "run-123",
                                        "allowed_side_effects": ["cancel_run"],
                                        "proposal": _proposal().model_dump(mode="python"),
                                        "verification_spec": _verification_spec().model_dump(mode="python"),
                                        "policy": {
                                            "policy_id": "policy-1",
                                            "description": "Observe, execute allowed cancel action, then verify.",
                                        },
                                    },
                                ],
                            },
                        }
                    ]
                )
            },
        ),
        role_policy=RoleModelPolicy(role_profiles={AgentRole.PLANNER.value: "planner-profile"}),
    )
    session = TaskSession(
        session_id="session-1",
        goal="Cancel the blocked run",
        target_kind=EntityKind.RUN,
        target_id="run-123",
        active_model_profile="planner-profile",
        memory_context={"bootstrap": {"hint": "Prefer evidence-backed planning."}},
    )

    contract, plan, result = PlannerAgent(model_client=runtime).plan(
        session_id=session.session_id,
        goal=session.goal,
        target_kind=session.target_kind,
        target_id=session.target_id,
        proposal=_proposal(),
        verification_spec=_verification_spec(),
        session=session,
    )

    assert contract.contract_id == "contract-1"
    assert len(plan.steps) == 1
    assert plan.steps[0].kind == TaskStepKind.DYNAMIC
    assert result.payload["model_trace_refs"]
    assert len(session.model_trace) == 1
    assert session.model_trace[0].profile_name == "planner-profile"


def test_planner_agent_fallback_always_generates_dynamic_step_for_plain_goal() -> None:
    contract, plan, _ = PlannerAgent().plan(
        session_id="session-1",
        goal="Cancel the blocked run",
        target_kind=EntityKind.RUN,
        target_id="run-123",
        proposal=_proposal(),
        verification_spec=_verification_spec(),
        session=TaskSession(
            session_id="session-1",
            goal="Cancel the blocked run",
            target_kind=EntityKind.RUN,
            target_id="run-123",
        ),
    )

    assert contract.contract_id.startswith("task-contract:")
    assert len(plan.steps) == 1
    assert plan.steps[0].kind == TaskStepKind.DYNAMIC
    assert plan.steps[0].proposal is not None
    assert plan.steps[0].policy is not None


def test_planner_agent_raises_when_model_output_is_invalid() -> None:
    runtime = ModelRuntime(
        ModelRegistry(
            profiles=[ModelProfile(name="planner-profile", provider="noop", model="noop-model")],
            clients={"noop": NoopModelClient(responses=[{"contract": {"contract_id": "missing-fields"}}])},
        ),
        role_policy=RoleModelPolicy(role_profiles={AgentRole.PLANNER.value: "planner-profile"}),
    )

    try:
        PlannerAgent(model_client=runtime).plan(
            session_id="session-1",
            goal="Cancel the blocked run",
            target_kind=EntityKind.RUN,
            target_id="run-123",
            proposal=_proposal(),
            verification_spec=_verification_spec(),
            session=TaskSession(
                session_id="session-1",
                goal="Cancel the blocked run",
                target_kind=EntityKind.RUN,
                target_id="run-123",
                active_model_profile="planner-profile",
            ),
        )
    except ValueError as exc:
        assert "failed validation" in str(exc)
    else:
        raise AssertionError("Expected planner model validation to fail.")
