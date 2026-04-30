from mobiflow_agent.agents.contracts import AgentRole, StepDecisionType
from mobiflow_agent.agents.step_policy import StepPolicyAgent
from mobiflow_agent.common.contracts import EntityKind, ExecutionProposal, VerificationCheck, VerificationSpec
from mobiflow_agent.model import ModelProfile, ModelRegistry, ModelRuntime, RoleModelPolicy
from mobiflow_agent.model.providers import NoopModelClient
from mobiflow_agent.task.plan import TaskPlan, TaskStep, TaskStepKind, TaskStepPolicy
from mobiflow_agent.task.session import TaskSession


def _dynamic_session(*, active_model_profile: str | None = None) -> TaskSession:
    spec = VerificationSpec(
        verification_id="verification:task",
        target_kind=EntityKind.TASK,
        target_id="task-1",
        success_checks=[
            VerificationCheck(
                check_id="home-visible",
                description="Home screen is visible.",
                evidence_hint="Home Screen",
            )
        ],
    )
    step = TaskStep(
        step_id="dynamic-step",
        kind=TaskStepKind.DYNAMIC,
        goal="Reach home screen.",
        verification_target_kind=EntityKind.TASK,
        verification_target_id="task-1",
        verification_spec=spec,
        allowed_side_effects=["mobile.tap"],
        policy=TaskStepPolicy(policy_id="policy-1", description="Bounded UI policy."),
    )
    return TaskSession(
        session_id="session-1",
        goal="Reach home screen.",
        target_kind=EntityKind.TASK,
        target_id="task-1",
        initial_verification_spec=spec,
        active_verification_spec=spec,
        plan=TaskPlan(plan_id="plan-1", summary="Dynamic plan.", steps=[step]),
        current_step=step,
        active_model_profile=active_model_profile,
    )


def test_step_policy_agent_uses_model_runtime_for_structured_decision() -> None:
    proposal = ExecutionProposal(
        proposal_id="proposal:model:tap",
        action_tool_name="mobile.tap",
        arguments={"node_id": "continue"},
        target_kind=EntityKind.TASK,
        target_id="task-1",
        rationale="Tap continue.",
    )
    runtime = ModelRuntime(
        ModelRegistry(
            profiles=[ModelProfile(name="step-profile", provider="noop", model="noop-model")],
            clients={
                "noop": NoopModelClient(
                    responses=[
                        {
                            "decision_id": "decision:model",
                            "decision_type": "propose_execution",
                            "summary": "Model proposes tapping continue.",
                            "proposal": proposal.model_dump(mode="python"),
                        }
                    ]
                )
            },
        ),
        role_policy=RoleModelPolicy(role_profiles={AgentRole.STEP_POLICY.value: "step-profile"}),
    )
    session = _dynamic_session(active_model_profile="step-profile")

    decision, result = StepPolicyAgent(model_client=runtime).decide(session)

    assert decision.decision_type == StepDecisionType.PROPOSE_EXECUTION
    assert decision.proposal == proposal
    assert result.payload["model_trace_refs"]
    assert len(session.model_trace) == 1


def test_step_policy_agent_falls_back_when_model_is_not_configured() -> None:
    session = _dynamic_session(active_model_profile=None)

    decision, result = StepPolicyAgent().decide(session)

    assert decision.decision_type == StepDecisionType.OBSERVE_AGAIN
    assert result.payload["model_trace_refs"] == []
