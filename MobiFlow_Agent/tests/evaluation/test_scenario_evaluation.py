from __future__ import annotations

from mobiflow_agent.common.contracts import VerificationStatus
from mobiflow_agent.evaluation.scenario import (
    ScenarioEvaluationReport,
    ScenarioEvaluationService,
    ScenarioMemoryEvaluationService,
    approval_required_destructive_action_case,
    dynamic_approval_required_destructive_action_case,
    dynamic_fixed_script_contrast_case,
    dynamic_login_success_case,
    dynamic_recovery_retry_success_case,
    dynamic_slow_loading_recovery_success_case,
    FixedScriptBaselineRunner,
    FixedScriptStep,
    handoff_followup_case,
    login_success_case,
    memory_writeback_quality_rejects_unknown_case,
    missing_password_blocked_case,
    wrong_button_no_success_case,
)
from mobiflow_agent.memory import InMemoryTaskMemoryStore, TaskMemoryRuntime
from mobiflow_agent.runtime.harness import TaskHarnessStatus


def test_scenario_evaluation_service_defaults_to_task_graph_runtime(monkeypatch) -> None:
    from mobiflow_agent.evaluation.scenario import service as scenario_service
    from mobiflow_agent.graph import TaskGraphRuntime

    created = []

    class SpyTaskGraphRuntime(TaskGraphRuntime):
        def __init__(self, *args, **kwargs):
            created.append(self)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(scenario_service, "TaskGraphRuntime", SpyTaskGraphRuntime)

    result = scenario_service.ScenarioEvaluationService().run_case(login_success_case())

    assert created
    assert all(isinstance(runtime, TaskGraphRuntime) for runtime in created)
    assert result.matched is True


def test_login_success_scenario_passes_quality_gate() -> None:
    result = ScenarioEvaluationService().run_case(login_success_case())

    assert result.matched is True
    assert result.final_response.status == TaskHarnessStatus.COMPLETED
    assert result.final_response.latest_verdict is not None
    assert result.final_response.latest_verdict.status == VerificationStatus.VERIFIED_SUCCESS
    assert [trace.action_tool_name for trace in result.action_traces] == [
        "mobile.launch",
        "mobile.input_text",
        "mobile.input_text",
        "mobile.tap",
    ]


def test_missing_password_scenario_keeps_blocked_verdict() -> None:
    result = ScenarioEvaluationService().run_case(missing_password_blocked_case())

    assert result.matched is True
    assert result.final_response.status == TaskHarnessStatus.HANDED_OFF
    assert result.final_response.latest_verdict is not None
    assert result.final_response.latest_verdict.status == VerificationStatus.BLOCKED
    assert result.final_response.latest_verdict.blocked_reason == "missing password"


def test_wrong_button_scenario_fails_without_evidence_success() -> None:
    result = ScenarioEvaluationService().run_case(wrong_button_no_success_case())

    assert result.matched is True
    assert result.final_response.status == TaskHarnessStatus.HANDED_OFF
    assert result.final_response.latest_verdict is not None
    assert result.final_response.latest_verdict.status == VerificationStatus.VERIFIED_UNKNOWN
    assert "mobile.input_text" not in [trace.action_tool_name for trace in result.action_traces]


def test_approval_required_scenario_observes_pause_and_then_completes() -> None:
    result = ScenarioEvaluationService().run_case(approval_required_destructive_action_case())

    assert result.matched is True
    assert any(response.status == TaskHarnessStatus.AWAITING_APPROVAL for response in result.responses)
    assert result.final_response.status == TaskHarnessStatus.COMPLETED
    assert result.action_traces[0].state.value == "approval_required"
    assert result.action_traces[-1].approved is True


def test_dynamic_login_scenario_uses_step_policy_loop() -> None:
    result = ScenarioEvaluationService().run_case(dynamic_login_success_case())

    assert result.matched is True
    assert result.final_response.status == TaskHarnessStatus.COMPLETED
    assert [trace.action_tool_name for trace in result.action_traces] == [
        "mobile.launch",
        "mobile.input_text",
        "mobile.input_text",
        "mobile.tap",
    ]


def test_dynamic_approval_scenario_observes_pause_and_then_completes() -> None:
    result = ScenarioEvaluationService().run_case(dynamic_approval_required_destructive_action_case())

    assert result.matched is True
    assert any(response.status == TaskHarnessStatus.AWAITING_APPROVAL for response in result.responses)
    assert result.final_response.status == TaskHarnessStatus.COMPLETED
    assert result.action_traces[0].state.value == "approval_required"
    assert result.action_traces[-1].approved is True


def test_dynamic_recovery_retry_scenario_completes_after_replan() -> None:
    result = ScenarioEvaluationService().run_case(dynamic_recovery_retry_success_case())

    assert result.matched is True
    assert result.final_response.status == TaskHarnessStatus.COMPLETED
    assert result.final_response.latest_verdict is not None
    assert result.final_response.latest_verdict.status == VerificationStatus.VERIFIED_SUCCESS


def test_dynamic_slow_loading_recovery_scenario_completes_after_replan() -> None:
    result = ScenarioEvaluationService().run_case(dynamic_slow_loading_recovery_success_case())

    assert result.matched is True
    assert result.final_response.status == TaskHarnessStatus.COMPLETED
    assert result.final_response.latest_verdict is not None
    assert result.final_response.latest_verdict.status == VerificationStatus.VERIFIED_SUCCESS


def test_fixed_script_baseline_fails_where_dynamic_agent_handles_permission_dialog() -> None:
    case = dynamic_fixed_script_contrast_case()
    script_result = FixedScriptBaselineRunner().run(
        case.platform_scenario,
        [
            FixedScriptStep(action_tool_name="mobile.launch", arguments={"app": "demo"}),
            FixedScriptStep(action_tool_name="mobile.input_text", arguments={"node_id": "username", "text": "alice"}),
            FixedScriptStep(action_tool_name="mobile.input_text", arguments={"node_id": "password", "text": "secret"}),
            FixedScriptStep(action_tool_name="mobile.tap", arguments={"node_id": "login_button"}),
        ],
    )
    agent_result = ScenarioEvaluationService().run_case(case)

    assert script_result.completed is False
    assert script_result.failed_step_index == 1
    assert script_result.final_screen_id == "permission"
    assert agent_result.matched is True
    assert agent_result.final_response.status == TaskHarnessStatus.COMPLETED


def test_handoff_followup_scenario_completes_after_heartbeat_tick() -> None:
    result = ScenarioEvaluationService().run_case(handoff_followup_case())

    assert result.matched is True
    assert any(response.status == TaskHarnessStatus.SCHEDULED for response in result.responses)
    assert result.final_response.status == TaskHarnessStatus.COMPLETED
    assert result.final_response.latest_verdict is not None
    assert result.final_response.latest_verdict.status == VerificationStatus.VERIFIED_SUCCESS


def test_scenario_report_summarizes_multiple_cases() -> None:
    service = ScenarioEvaluationService()
    report = service.run_cases([login_success_case(), wrong_button_no_success_case()])

    assert isinstance(report, ScenarioEvaluationReport)
    assert report.total_cases == 2
    assert report.matched_cases == 2
    assert report.mismatched_cases == 0


def test_scenario_memory_comparison_reports_hits_writeback_and_quality_rejections() -> None:
    service = ScenarioMemoryEvaluationService(
        memory_runtime_factory=lambda: TaskMemoryRuntime(store=InMemoryTaskMemoryStore())
    )

    result = service.compare_case(memory_writeback_quality_rejects_unknown_case())

    assert result.outcome.value == "unchanged"
    assert result.memory_off_result.matched is True
    assert result.memory_on_result.matched is True
    assert result.quarantined_count > 0
    assert result.quality_rejection_count == 0
