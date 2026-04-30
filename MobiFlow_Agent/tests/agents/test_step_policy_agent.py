from mobiflow_agent.agents.contracts import AgentRole, StepDecisionType
from mobiflow_agent.agents.step_policy import StepPolicyAgent
from mobiflow_agent.common.contracts import (
    EntityKind,
    EvidenceKind,
    EvidenceRef,
    ExecutionProposal,
    ObservationFact,
    ObservationFactSource,
    ObservationView,
    VerificationCheck,
    VerificationSpec,
)
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
    assert result.payload["decision_source"] == "model"
    assert result.payload["validation"]["accepted"] is True
    assert result.payload["model_trace_refs"]
    assert len(session.model_trace) == 1


def test_step_policy_agent_falls_back_when_model_is_not_configured() -> None:
    session = _dynamic_session(active_model_profile=None)

    decision, result = StepPolicyAgent().decide(session)

    assert decision.decision_type == StepDecisionType.OBSERVE_AGAIN
    assert result.payload["decision_source"] == "fallback"
    assert result.payload["fallback_decision"]["decision_type"] == StepDecisionType.OBSERVE_AGAIN.value
    assert result.payload["model_trace_refs"] == []


def test_step_policy_agent_rejects_model_proposal_outside_allowlist() -> None:
    proposal = ExecutionProposal(
        proposal_id="proposal:model:delete",
        action_tool_name="mobile.delete",
        arguments={"node_id": "delete"},
        target_kind=EntityKind.TASK,
        target_id="task-1",
        rationale="Delete outside allowlist.",
    )
    runtime = _runtime_with_response(
        {
            "decision_id": "decision:bad-tool",
            "decision_type": "propose_execution",
            "summary": "Model proposes an unsafe tool.",
            "proposal": proposal.model_dump(mode="python"),
        }
    )
    session = _dynamic_session(active_model_profile="step-profile")

    decision, result = StepPolicyAgent(model_client=runtime).decide(session)

    assert decision.decision_type == StepDecisionType.OBSERVE_AGAIN
    assert "proposal_action_not_allowed" in decision.summary
    assert result.payload["decision_source"] == "fallback"
    assert result.payload["validation"]["accepted"] is False
    assert "proposal_action_not_allowed" in result.payload["validation"]["issues"]
    assert result.payload["model_decision"]["decision_id"] == "decision:bad-tool"
    assert result.payload["fallback_decision"]["decision_type"] == StepDecisionType.OBSERVE_AGAIN.value
    assert result.payload["model_trace_refs"]


def test_step_policy_agent_rejects_model_proposal_with_wrong_target() -> None:
    proposal = ExecutionProposal(
        proposal_id="proposal:model:wrong-target",
        action_tool_name="mobile.tap",
        arguments={"node_id": "continue"},
        target_kind=EntityKind.TASK,
        target_id="other-task",
        rationale="Tap another task.",
    )
    runtime = _runtime_with_response(
        {
            "decision_id": "decision:wrong-target",
            "decision_type": "propose_execution",
            "summary": "Model proposes another target.",
            "proposal": proposal.model_dump(mode="python"),
        }
    )
    session = _dynamic_session(active_model_profile="step-profile")

    decision, _ = StepPolicyAgent(model_client=runtime).decide(session)

    assert decision.decision_type == StepDecisionType.OBSERVE_AGAIN
    assert "proposal_target_id_mismatch" in decision.summary


def test_step_policy_agent_rejects_premature_model_success_without_observation() -> None:
    runtime = _runtime_with_response(
        {
            "decision_id": "decision:premature-success",
            "decision_type": "step_succeeded",
            "summary": "Model claims success too early.",
        }
    )
    session = _dynamic_session(active_model_profile="step-profile")

    decision, _ = StepPolicyAgent(model_client=runtime).decide(session)

    assert decision.decision_type == StepDecisionType.OBSERVE_AGAIN
    assert "success_without_observation" in decision.summary


def test_step_policy_agent_accepts_success_when_observation_satisfies_spec() -> None:
    runtime = _runtime_with_response(
        {
            "decision_id": "decision:success",
            "decision_type": "step_succeeded",
            "summary": "Model sees home screen evidence.",
        }
    )
    session = _dynamic_session(active_model_profile="step-profile")
    session.last_observation = ObservationView(
        observation_id="observe-home",
        focus_kind=EntityKind.TASK,
        focus_id="task-1",
        facts=[
            ObservationFact(
                fact_id="screen",
                source=ObservationFactSource.PLATFORM,
                title="Screen",
                value={"title": "Home Screen"},
                evidence_refs=[
                    EvidenceRef(
                        evidence_id="evidence-home",
                        kind=EvidenceKind.PLATFORM_SNAPSHOT,
                        summary="Home Screen is visible.",
                        locator="task-1",
                    )
                ],
            )
        ],
    )

    decision, _ = StepPolicyAgent(model_client=runtime).decide(session)

    assert decision.decision_type == StepDecisionType.STEP_SUCCEEDED


def _runtime_with_response(response) -> ModelRuntime:
    return ModelRuntime(
        ModelRegistry(
            profiles=[ModelProfile(name="step-profile", provider="noop", model="noop-model")],
            clients={"noop": NoopModelClient(responses=[response])},
        ),
        role_policy=RoleModelPolicy(role_profiles={AgentRole.STEP_POLICY.value: "step-profile"}),
    )
