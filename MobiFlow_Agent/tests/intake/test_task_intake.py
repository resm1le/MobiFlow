from mobiflow_agent.agents import ExecutorAgent, ObserverAgent
from mobiflow_agent.common import EntityKind
from mobiflow_agent.control import TaskControlPolicy
from mobiflow_agent.evaluation.scenario import dynamic_login_success_case
from mobiflow_agent.graph import TaskGraphRuntime
from mobiflow_agent.intake import (
    ScenarioTemplateRegistry,
    TaskIntakeService,
    TaskIntakeSpec,
    TaskIntakeStatus,
    TaskIntakeValidator,
    TaskInterpreter,
)
from mobiflow_agent.platform.simulation import SimulatedMobilePlatformAdapter
from mobiflow_agent.task import TaskStatus, TaskStepKind


def test_task_interpreter_maps_chinese_login_goal_to_dynamic_template() -> None:
    result = TaskInterpreter().interpret("登录 demo app 并验证进入首页")

    assert result.status == TaskIntakeStatus.READY
    assert result.spec is not None
    assert result.spec.scenario_id == "dynamic_login_success"
    assert result.spec.normalized_goal == "Login to the demo app using bounded mobile UI actions."
    assert not result.spec.normalized_goal.startswith("[dynamic]")


def test_task_intake_service_creates_dynamic_session_from_english_goal() -> None:
    result = TaskIntakeService().create_session_from_text("Login to the demo app and reach home screen.")

    assert result.status == TaskIntakeStatus.READY
    assert result.session is not None
    assert result.session.target_id == "dynamic_login_success"
    assert result.session.initial_verification_spec is not None
    assert result.session.initial_verification_spec.verification_id.startswith("verification:task:dynamic_login_success")


def test_task_intake_rejects_unknown_goal_without_session() -> None:
    result = TaskIntakeService().create_session_from_text("Run a completely unknown mobile experiment.")

    assert result.status == TaskIntakeStatus.NEEDS_CLARIFICATION
    assert result.session is None
    assert "unknown_scenario_id" in result.issues


def test_task_intake_requires_confirmation_for_high_risk_template() -> None:
    service = TaskIntakeService()

    blocked = service.create_session_from_text("删除账号并验证删除完成")
    confirmed = service.create_session_from_text("删除账号并验证删除完成", confirmed=True)

    assert blocked.status == TaskIntakeStatus.NEEDS_CLARIFICATION
    assert "confirmation_required" in blocked.issues
    assert confirmed.status == TaskIntakeStatus.READY
    assert confirmed.session is not None
    assert confirmed.session.target_id == "dynamic_approval_required_destructive_action"


def test_task_intake_validator_rejects_illegal_template_fields() -> None:
    spec = TaskIntakeSpec(
        raw_goal="Login.",
        normalized_goal="Login.",
        scenario_id="dynamic_login_success",
        target_kind=EntityKind.TASK,
        target_id="dynamic_login_success",
        verification_template="account_deleted_visible",
        allowed_actions=["mobile.shell"],
    )

    validation = TaskIntakeValidator(template_registry=ScenarioTemplateRegistry.default()).validate(spec)

    assert validation.accepted is False
    assert "verification_template_mismatch" in validation.issues
    assert "disallowed_action:mobile.shell" in validation.issues


def test_task_intake_session_runs_dynamic_login_flow() -> None:
    case = dynamic_login_success_case()
    adapter = SimulatedMobilePlatformAdapter(case.platform_scenario, target_id=case.scenario_id)
    runtime = TaskGraphRuntime(
        observer_agent=ObserverAgent(adapter=adapter),
        executor_agent=ExecutorAgent(adapter),
        policy=TaskControlPolicy(allow_recovery=case.allow_recovery),
    )
    intake = TaskIntakeService(runtime=runtime)

    result = intake.create_session_from_text("登录 demo app 并验证进入首页")
    assert result.status == TaskIntakeStatus.READY
    assert result.session is not None

    completed = runtime.run(result.session)

    assert completed.status == TaskStatus.COMPLETED
    assert completed.plan is not None
    assert [step.kind for step in completed.plan.steps] == [TaskStepKind.DYNAMIC]
    assert completed.last_verdict is not None
    assert completed.last_verdict.status.value == "verified_success"
