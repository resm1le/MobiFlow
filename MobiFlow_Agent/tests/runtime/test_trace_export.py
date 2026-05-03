from mobiflow_agent.common.contracts import EntityKind, ExecutionProposal
from mobiflow_agent.agents import AgentRole, StepPolicyAgent
from mobiflow_agent.model import ModelProfile, ModelRegistry, ModelRuntime, RoleModelPolicy
from mobiflow_agent.model.providers import NoopModelClient
from mobiflow_agent.evaluation.scenario import dynamic_slow_loading_recovery_success_case
from mobiflow_agent.graph import TaskGraphRuntime
from mobiflow_agent.agents import ExecutorAgent, ObserverAgent
from mobiflow_agent.control import TaskControlPolicy
from mobiflow_agent.platform.simulation import SimulatedMobilePlatformAdapter
from mobiflow_agent.runtime.trace_export import ExecutionTraceExporter
from mobiflow_agent.task.plan import TaskPlan, TaskStep, TaskStepKind, TaskStepPolicy
from mobiflow_agent.task.session import TaskSession


def test_execution_trace_exporter_outputs_json_and_markdown_without_sensitive_payload() -> None:
    proposal = ExecutionProposal(
        proposal_id="proposal-1",
        action_tool_name="mobile.input_text",
        arguments={"node_id": "password", "password": "secret"},
        target_kind=EntityKind.TASK,
        target_id="task-1",
        rationale="Enter password.",
    )
    step = TaskStep(
        step_id="step-1",
        kind=TaskStepKind.DYNAMIC,
        goal="Enter password and verify login progress.",
        proposal=proposal,
        allowed_side_effects=["mobile.input_text"],
        policy=TaskStepPolicy(
            policy_id="policy-1",
            description="Dynamic trace export test policy.",
        ),
    )
    session = TaskSession(
        session_id="session-1",
        goal="Login.",
        target_kind=EntityKind.TASK,
        target_id="task-1",
        initial_proposal=proposal,
        plan=TaskPlan(plan_id="plan-1", summary="Login plan.", steps=[step]),
        current_step=step,
    )

    exporter = ExecutionTraceExporter()
    exported = exporter.export_json(session)
    markdown = exporter.export_markdown(session)
    dumped = exporter.dumps_json(session)

    assert exported["session_id"] == "session-1"
    assert exported["plan"]["steps"][0]["proposal"]["arguments"]["password"] == "[REDACTED]"
    assert "secret" not in dumped
    assert "# Execution Trace: session-1" in markdown
    assert "Login plan." in markdown


def test_execution_trace_exporter_timeline_shows_rejected_model_decision(artifact_tmp_path) -> None:
    proposal = ExecutionProposal(
        proposal_id="proposal:unsafe",
        action_tool_name="mobile.delete",
        arguments={"node_id": "delete"},
        target_kind=EntityKind.TASK,
        target_id="task-1",
        rationale="Unsafe model proposal.",
    )
    step = TaskStep(
        step_id="dynamic-step",
        kind=TaskStepKind.DYNAMIC,
        goal="Reach safe state.",
        allowed_side_effects=["mobile.tap"],
        policy=TaskStepPolicy(policy_id="policy-1", description="Observe before acting."),
    )
    session = TaskSession(
        session_id="session-rejected-model",
        goal="Reach safe state.",
        target_kind=EntityKind.TASK,
        target_id="task-1",
        plan=TaskPlan(plan_id="plan-1", summary="Dynamic plan.", steps=[step]),
        current_step=step,
        active_model_profile="step-profile",
    )
    runtime = ModelRuntime(
        ModelRegistry(
            profiles=[ModelProfile(name="step-profile", provider="noop", model="noop-model")],
            clients={
                "noop": NoopModelClient(
                    responses=[
                        {
                            "decision_id": "decision:unsafe",
                            "decision_type": "propose_execution",
                            "summary": "Model proposes an unsafe delete.",
                            "proposal": proposal.model_dump(mode="python"),
                        }
                    ]
                )
            },
        ),
        role_policy=RoleModelPolicy(role_profiles={AgentRole.STEP_POLICY.value: "step-profile"}),
    )

    _, role_result = StepPolicyAgent(model_client=runtime).decide(session)
    session.role_results.append(role_result)
    exporter = ExecutionTraceExporter()
    trace = exporter.export_json(session)
    json_path = exporter.write_json(session, artifact_tmp_path / "trace.json")
    markdown_path = exporter.write_markdown(session, artifact_tmp_path / "trace.md")

    decision_items = [item for item in trace["timeline"] if item["node"] == "decide_step"]
    assert decision_items[0]["validation"]["accepted"] is False
    assert "proposal_action_not_allowed" in decision_items[0]["validation"]["issues"]
    assert decision_items[0]["model_decision"]["decision_id"] == "decision:unsafe"
    assert decision_items[0]["fallback_decision"]["decision_type"] == "observe_again"
    assert json_path.exists()
    assert markdown_path.read_text(encoding="utf-8").find("validation: accepted=False") >= 0


def test_execution_trace_exporter_includes_recovery_timeline_for_dynamic_case() -> None:
    case = dynamic_slow_loading_recovery_success_case()
    adapter = SimulatedMobilePlatformAdapter(case.platform_scenario, target_id=case.scenario_id)
    runtime = TaskGraphRuntime(
        observer_agent=ObserverAgent(adapter=adapter),
        executor_agent=ExecutorAgent(adapter),
        policy=TaskControlPolicy(allow_recovery=True),
    )
    request = case.requests[0]
    session = runtime.run(
        runtime.create_session(
            request.goal,
            target_kind=request.target_kind,
            target_id=request.target_id,
            proposal=request.proposal,
            verification_spec=request.verification_spec,
        )
    )

    trace = ExecutionTraceExporter().export_json(session, action_traces=adapter.action_traces)
    markdown = ExecutionTraceExporter().export_markdown(session, action_traces=adapter.action_traces)
    nodes = [item["node"] for item in trace["timeline"]]

    assert "observe" in nodes
    assert "decide_step" in nodes
    assert "recover" in nodes
    assert "verify" in nodes
    assert "## Timeline" in markdown
    assert "recover" in markdown
