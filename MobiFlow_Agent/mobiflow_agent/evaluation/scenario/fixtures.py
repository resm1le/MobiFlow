from __future__ import annotations

from mobiflow_agent.common.contracts import (
    EntityKind,
    ExecutionProposal,
    VerificationCheck,
    VerificationSpec,
    VerificationStatus,
)
from mobiflow_agent.evaluation.scenario.models import ScenarioEvaluationCase, ScenarioExpectation
from mobiflow_agent.platform.simulation import (
    SimulatedMobileScenario,
    SimulatedScreen,
    SimulatedTransition,
    SimulatedUiNode,
)
from mobiflow_agent.runtime.harness import TaskHarnessJobPolicy, TaskHarnessRequest, TaskHarnessStatus


def login_success_case() -> ScenarioEvaluationCase:
    scenario = _login_scenario()
    scenario_id = scenario.scenario_id
    return ScenarioEvaluationCase(
        scenario_id=scenario_id,
        name="login_success",
        platform_scenario=scenario,
        requests=[
            _request(
                scenario_id,
                goal="Launch the demo app.",
                proposal=_proposal("launch", "mobile.launch", {"app": "demo"}, scenario_id),
                success_text="Login Screen",
            ),
            _request(
                scenario_id,
                goal="Enter username.",
                proposal=_proposal(
                    "username",
                    "mobile.input_text",
                    {"node_id": "username", "text": "alice"},
                    scenario_id,
                ),
                success_text="username alice",
            ),
            _request(
                scenario_id,
                goal="Enter password.",
                proposal=_proposal(
                    "password",
                    "mobile.input_text",
                    {"node_id": "password", "text": "secret"},
                    scenario_id,
                ),
                success_text="password entered",
            ),
            _request(
                scenario_id,
                goal="Submit login.",
                proposal=_proposal("submit", "mobile.tap", {"node_id": "login_button"}, scenario_id),
                success_text="Home Screen",
            ),
        ],
        expectation=ScenarioExpectation(
            expected_final_status=TaskHarnessStatus.COMPLETED,
            expected_verification_status=VerificationStatus.VERIFIED_SUCCESS,
            required_actions=["mobile.launch", "mobile.input_text", "mobile.tap"],
        ),
        allow_recovery=False,
    )


def dynamic_login_success_case() -> ScenarioEvaluationCase:
    scenario = _login_scenario(scenario_id="dynamic_login_success")
    scenario_id = scenario.scenario_id
    return ScenarioEvaluationCase(
        scenario_id=scenario_id,
        name=scenario_id,
        platform_scenario=scenario,
        requests=[
            TaskHarnessRequest(
                goal="[dynamic] Login to the demo app using bounded mobile UI actions.",
                target_kind=EntityKind.TASK,
                target_id=scenario_id,
                verification_spec=_verification_spec(scenario_id, "Home Screen"),
            )
        ],
        expectation=ScenarioExpectation(
            expected_final_status=TaskHarnessStatus.COMPLETED,
            expected_verification_status=VerificationStatus.VERIFIED_SUCCESS,
            required_actions=["mobile.launch", "mobile.input_text", "mobile.tap"],
        ),
        allow_recovery=False,
    )


def missing_password_blocked_case() -> ScenarioEvaluationCase:
    scenario = _login_scenario(scenario_id="missing_password_blocked")
    scenario_id = scenario.scenario_id
    return ScenarioEvaluationCase(
        scenario_id=scenario_id,
        name="missing_password_blocked",
        platform_scenario=scenario,
        requests=[
            _request(
                scenario_id,
                goal="Launch app.",
                proposal=_proposal("launch", "mobile.launch", {"app": "demo"}, scenario_id),
                success_text="Login Screen",
            ),
            _request(
                scenario_id,
                goal="Submit login without password.",
                proposal=_proposal("submit-empty", "mobile.tap", {"node_id": "login_button"}, scenario_id),
                success_text="Home Screen",
                blocked_conditions=["missing password"],
            ),
        ],
        expectation=ScenarioExpectation(
            expected_final_status=TaskHarnessStatus.HANDED_OFF,
            expected_verification_status=VerificationStatus.BLOCKED,
            required_actions=["mobile.launch", "mobile.tap"],
        ),
        allow_recovery=False,
    )


def approval_required_destructive_action_case() -> ScenarioEvaluationCase:
    scenario_id = "approval_required_destructive_action"
    scenario = SimulatedMobileScenario(
        scenario_id=scenario_id,
        name="Approval required destructive action",
        initial_screen_id="settings",
        screens={
            "settings": SimulatedScreen(
                screen_id="settings",
                title="Settings Screen",
                nodes=[SimulatedUiNode(node_id="delete_button", role="button", text="Delete account")],
            ),
            "deleted": SimulatedScreen(
                screen_id="deleted",
                title="Account Deleted Screen",
                nodes=[SimulatedUiNode(node_id="deleted_message", text="Account deleted")],
            ),
        },
        transitions=[
            SimulatedTransition(
                action_tool_name="mobile.tap",
                from_screen_id="settings",
                to_screen_id="deleted",
                match_arguments={"node_id": "delete_button"},
                requires_approval=True,
                confirmation_summary="Approve deleting the simulated account.",
            )
        ],
    )
    return ScenarioEvaluationCase(
        scenario_id=scenario_id,
        name=scenario_id,
        platform_scenario=scenario,
        requests=[
            _request(
                scenario_id,
                goal="Delete the simulated account after approval.",
                proposal=_proposal("delete", "mobile.tap", {"node_id": "delete_button"}, scenario_id),
                success_text="Account Deleted Screen",
            )
        ],
        expectation=ScenarioExpectation(
            expected_final_status=TaskHarnessStatus.COMPLETED,
            expected_verification_status=VerificationStatus.VERIFIED_SUCCESS,
            required_actions=["mobile.tap"],
            expect_approval_pause=True,
        ),
        approval_decisions={0: True},
        allow_recovery=False,
    )


def dynamic_approval_required_destructive_action_case() -> ScenarioEvaluationCase:
    base = approval_required_destructive_action_case()
    scenario_id = "dynamic_approval_required_destructive_action"
    scenario = base.platform_scenario.model_copy(
        update={
            "scenario_id": scenario_id,
            "name": "Dynamic approval required destructive action",
        },
        deep=True,
    )
    return ScenarioEvaluationCase(
        scenario_id=scenario_id,
        name=scenario_id,
        platform_scenario=scenario,
        requests=[
            TaskHarnessRequest(
                goal="[dynamic] Delete the simulated account after approval.",
                target_kind=EntityKind.TASK,
                target_id=scenario_id,
                verification_spec=_verification_spec(scenario_id, "Account Deleted Screen"),
            )
        ],
        expectation=ScenarioExpectation(
            expected_final_status=TaskHarnessStatus.COMPLETED,
            expected_verification_status=VerificationStatus.VERIFIED_SUCCESS,
            required_actions=["mobile.tap"],
            expect_approval_pause=True,
        ),
        approval_decisions={0: True},
        allow_recovery=False,
    )


def dynamic_recovery_retry_success_case() -> ScenarioEvaluationCase:
    scenario_id = "dynamic_recovery_retry_success"
    scenario = SimulatedMobileScenario(
        scenario_id=scenario_id,
        name="Dynamic recovery retry success",
        initial_screen_id="retry_gate",
        screens={
            "retry_gate": SimulatedScreen(
                screen_id="retry_gate",
                title="Intermediate Screen",
                metadata={
                    "step_policy_blocked_reason": "dynamic_recovery_retry",
                    "auto_advance_to_after_observe": "home",
                },
                nodes=[SimulatedUiNode(node_id="retry_hint", text="Retry after replan")],
            ),
            "home": SimulatedScreen(
                screen_id="home",
                title="Home Screen",
                nodes=[SimulatedUiNode(node_id="home_title", text="Welcome home")],
            ),
        },
    )
    return ScenarioEvaluationCase(
        scenario_id=scenario_id,
        name=scenario_id,
        platform_scenario=scenario,
        requests=[
            TaskHarnessRequest(
                goal="[dynamic] Reach home screen through recovery retry.",
                target_kind=EntityKind.TASK,
                target_id=scenario_id,
                verification_spec=_verification_spec(scenario_id, "Home Screen"),
            )
        ],
        expectation=ScenarioExpectation(
            expected_final_status=TaskHarnessStatus.COMPLETED,
            expected_verification_status=VerificationStatus.VERIFIED_SUCCESS,
            expect_recovery_path=True,
        ),
        allow_recovery=True,
    )


def dynamic_slow_loading_recovery_success_case() -> ScenarioEvaluationCase:
    scenario_id = "dynamic_slow_loading_recovery_success"
    scenario = SimulatedMobileScenario(
        scenario_id=scenario_id,
        name="Dynamic slow loading recovery success",
        initial_screen_id="loading",
        screens={
            "loading": SimulatedScreen(
                screen_id="loading",
                title="Loading Screen",
                metadata={
                    "step_policy_blocked_reason": "slow_loading_screen",
                    "auto_advance_to_after_observe": "home",
                },
                nodes=[SimulatedUiNode(node_id="spinner", text="Loading")],
            ),
            "home": SimulatedScreen(
                screen_id="home",
                title="Home Screen",
                nodes=[SimulatedUiNode(node_id="home_title", text="Welcome home")],
            ),
        },
    )
    return ScenarioEvaluationCase(
        scenario_id=scenario_id,
        name=scenario_id,
        platform_scenario=scenario,
        requests=[
            TaskHarnessRequest(
                goal="[dynamic] Recover from slow loading and verify home screen.",
                target_kind=EntityKind.TASK,
                target_id=scenario_id,
                verification_spec=_verification_spec(scenario_id, "Home Screen"),
            )
        ],
        expectation=ScenarioExpectation(
            expected_final_status=TaskHarnessStatus.COMPLETED,
            expected_verification_status=VerificationStatus.VERIFIED_SUCCESS,
            expect_recovery_path=True,
        ),
        allow_recovery=True,
    )


def dynamic_fixed_script_contrast_case() -> ScenarioEvaluationCase:
    scenario = _login_scenario(scenario_id="dynamic_fixed_script_contrast").model_copy(deep=True)
    scenario = scenario.model_copy(
        update={
            "screens": {
                **scenario.screens,
                "permission": SimulatedScreen(
                    screen_id="permission",
                    title="Permission Dialog",
                    nodes=[SimulatedUiNode(node_id="allow_button", role="button", text="Allow")],
                ),
            },
            "transitions": [
                SimulatedTransition(
                    action_tool_name="mobile.launch",
                    from_screen_id="launcher",
                    to_screen_id="permission",
                    match_arguments={"app": "demo"},
                ),
                SimulatedTransition(
                    action_tool_name="mobile.tap",
                    from_screen_id="permission",
                    to_screen_id="login_blank",
                    match_arguments={"node_id": "allow_button"},
                ),
                *scenario.transitions[1:],
            ],
        },
        deep=True,
    )
    scenario_id = scenario.scenario_id
    return ScenarioEvaluationCase(
        scenario_id=scenario_id,
        name=scenario_id,
        platform_scenario=scenario,
        requests=[
            TaskHarnessRequest(
                goal="[dynamic] Login while handling unexpected permission dialog.",
                target_kind=EntityKind.TASK,
                target_id=scenario_id,
                verification_spec=_verification_spec(scenario_id, "Home Screen"),
            )
        ],
        expectation=ScenarioExpectation(
            expected_final_status=TaskHarnessStatus.COMPLETED,
            expected_verification_status=VerificationStatus.VERIFIED_SUCCESS,
            required_actions=["mobile.launch", "mobile.tap", "mobile.input_text"],
        ),
        allow_recovery=False,
    )


def wrong_button_no_success_case() -> ScenarioEvaluationCase:
    scenario = _login_scenario(scenario_id="wrong_button_no_success")
    scenario_id = scenario.scenario_id
    return ScenarioEvaluationCase(
        scenario_id=scenario_id,
        name="wrong_button_no_success",
        platform_scenario=scenario,
        requests=[
            _request(
                scenario_id,
                goal="Launch app.",
                proposal=_proposal("launch", "mobile.launch", {"app": "demo"}, scenario_id),
                success_text="Login Screen",
            ),
            _request(
                scenario_id,
                goal="Tap the wrong button.",
                proposal=_proposal("help", "mobile.tap", {"node_id": "help_button"}, scenario_id),
                success_text="Home Screen",
            ),
        ],
        expectation=ScenarioExpectation(
            expected_final_status=TaskHarnessStatus.HANDED_OFF,
            expected_verification_status=VerificationStatus.VERIFIED_UNKNOWN,
            required_actions=["mobile.tap"],
            forbidden_actions=["mobile.input_text"],
        ),
        allow_recovery=False,
    )


def handoff_followup_case() -> ScenarioEvaluationCase:
    scenario_id = "handoff_followup"
    scenario = SimulatedMobileScenario(
        scenario_id=scenario_id,
        name="Handoff follow-up",
        initial_screen_id="loading",
        screens={
            "loading": SimulatedScreen(
                screen_id="loading",
                title="Loading Screen",
                metadata={"auto_advance_to_after_observe": "home"},
                nodes=[SimulatedUiNode(node_id="loading", text="Loading")],
            ),
            "home": SimulatedScreen(
                screen_id="home",
                title="Home Screen",
                nodes=[SimulatedUiNode(node_id="home_title", text="Welcome home")],
            ),
        },
    )
    return ScenarioEvaluationCase(
        scenario_id=scenario_id,
        name=scenario_id,
        platform_scenario=scenario,
        requests=[
            TaskHarnessRequest(
                goal="Wait for home screen through handoff continuation.",
                target_kind=EntityKind.TASK,
                target_id=scenario_id,
                verification_spec=_verification_spec(scenario_id, "Home Screen"),
                policy=TaskHarnessJobPolicy(wake_interval_seconds=1, max_heartbeat_ticks=2, continue_on_handoff=True),
            )
        ],
        expectation=ScenarioExpectation(
            expected_final_status=TaskHarnessStatus.COMPLETED,
            expected_verification_status=VerificationStatus.VERIFIED_SUCCESS,
            expect_recovery_path=True,
        ),
        allow_recovery=False,
        heartbeat_ticks=1,
    )


def memory_guided_recovery_success_case() -> ScenarioEvaluationCase:
    scenario = _login_scenario(scenario_id="memory_guided_recovery_success")
    scenario_id = scenario.scenario_id
    return ScenarioEvaluationCase(
        scenario_id=scenario_id,
        name=scenario_id,
        platform_scenario=scenario,
        requests=[
            _request(
                scenario_id,
                goal="Launch app.",
                proposal=_proposal("launch", "mobile.launch", {"app": "demo"}, scenario_id),
                success_text="Login Screen",
            ),
            _request(
                scenario_id,
                goal="Submit login without password and rely on similar blocked memory.",
                proposal=_proposal("submit-empty", "mobile.tap", {"node_id": "login_button"}, scenario_id),
                success_text="Home Screen",
                blocked_conditions=["missing password"],
            ),
        ],
        expectation=ScenarioExpectation(
            expected_final_status=TaskHarnessStatus.HANDED_OFF,
            expected_verification_status=VerificationStatus.BLOCKED,
            required_actions=["mobile.launch", "mobile.tap"],
        ),
        allow_recovery=False,
    )


def memory_blocks_wrong_success_case() -> ScenarioEvaluationCase:
    scenario = _login_scenario(scenario_id="memory_blocks_wrong_success")
    scenario_id = scenario.scenario_id
    return ScenarioEvaluationCase(
        scenario_id=scenario_id,
        name=scenario_id,
        platform_scenario=scenario,
        requests=[
            _request(
                scenario_id,
                goal="Launch app.",
                proposal=_proposal("launch", "mobile.launch", {"app": "demo"}, scenario_id),
                success_text="Login Screen",
            ),
            _request(
                scenario_id,
                goal="Tap the wrong button despite similar success memory.",
                proposal=_proposal("help", "mobile.tap", {"node_id": "help_button"}, scenario_id),
                success_text="Home Screen",
            ),
        ],
        expectation=ScenarioExpectation(
            expected_final_status=TaskHarnessStatus.HANDED_OFF,
            expected_verification_status=VerificationStatus.VERIFIED_UNKNOWN,
            required_actions=["mobile.tap"],
            forbidden_actions=["mobile.input_text"],
        ),
        allow_recovery=False,
    )


def memory_writeback_quality_rejects_unknown_case() -> ScenarioEvaluationCase:
    scenario = _login_scenario(scenario_id="memory_writeback_quality_rejects_unknown")
    scenario_id = scenario.scenario_id
    return ScenarioEvaluationCase(
        scenario_id=scenario_id,
        name=scenario_id,
        platform_scenario=scenario,
        requests=[
            _request(
                scenario_id,
                goal="Launch app.",
                proposal=_proposal("launch", "mobile.launch", {"app": "demo"}, scenario_id),
                success_text="Login Screen",
            ),
            _request(
                scenario_id,
                goal="Tap help and produce unknown verification.",
                proposal=_proposal("help", "mobile.tap", {"node_id": "help_button"}, scenario_id),
                success_text="Home Screen",
            ),
        ],
        expectation=ScenarioExpectation(
            expected_final_status=TaskHarnessStatus.HANDED_OFF,
            expected_verification_status=VerificationStatus.VERIFIED_UNKNOWN,
            required_actions=["mobile.tap"],
        ),
        allow_recovery=False,
    )
def _login_scenario(*, scenario_id: str = "login_success") -> SimulatedMobileScenario:
    return SimulatedMobileScenario(
        scenario_id=scenario_id,
        name=scenario_id.replace("_", " ").title(),
        initial_screen_id="launcher",
        screens={
            "launcher": SimulatedScreen(
                screen_id="launcher",
                title="Launcher Screen",
                nodes=[SimulatedUiNode(node_id="app_icon", role="button", text="Demo")],
            ),
            "login_blank": SimulatedScreen(
                screen_id="login_blank",
                title="Login Screen",
                nodes=[
                    SimulatedUiNode(node_id="username", role="text_field", text="Username"),
                    SimulatedUiNode(node_id="password", role="text_field", text="Password"),
                    SimulatedUiNode(node_id="login_button", role="button", text="Log in"),
                    SimulatedUiNode(node_id="help_button", role="button", text="Help"),
                ],
            ),
            "username_entered": SimulatedScreen(
                screen_id="username_entered",
                title="Login Screen",
                metadata={"username": "alice"},
                nodes=[
                    SimulatedUiNode(node_id="username", role="text_field", text="Username", value="alice"),
                    SimulatedUiNode(node_id="password", role="text_field", text="Password"),
                    SimulatedUiNode(node_id="login_button", role="button", text="Log in"),
                ],
            ),
            "ready": SimulatedScreen(
                screen_id="ready",
                title="Login Screen",
                metadata={"username": "alice", "password": "password entered"},
                nodes=[
                    SimulatedUiNode(node_id="username", role="text_field", text="Username", value="alice"),
                    SimulatedUiNode(node_id="password", role="text_field", text="Password", value="password entered"),
                    SimulatedUiNode(node_id="login_button", role="button", text="Log in"),
                ],
            ),
            "home": SimulatedScreen(
                screen_id="home",
                title="Home Screen",
                nodes=[SimulatedUiNode(node_id="home_title", text="Welcome home")],
            ),
            "missing_password": SimulatedScreen(
                screen_id="missing_password",
                title="Login Screen",
                blocked_reason="missing password",
                nodes=[SimulatedUiNode(node_id="password_error", text="Missing password")],
            ),
            "help": SimulatedScreen(
                screen_id="help",
                title="Help Screen",
                nodes=[SimulatedUiNode(node_id="help_title", text="Help center")],
            ),
        },
        transitions=[
            SimulatedTransition(
                action_tool_name="mobile.launch",
                from_screen_id="launcher",
                to_screen_id="login_blank",
                match_arguments={"app": "demo"},
            ),
            SimulatedTransition(
                action_tool_name="mobile.input_text",
                from_screen_id="login_blank",
                to_screen_id="username_entered",
                match_arguments={"node_id": "username", "text": "alice"},
            ),
            SimulatedTransition(
                action_tool_name="mobile.input_text",
                from_screen_id="username_entered",
                to_screen_id="ready",
                match_arguments={"node_id": "password", "text": "secret"},
            ),
            SimulatedTransition(
                action_tool_name="mobile.tap",
                from_screen_id="ready",
                to_screen_id="home",
                match_arguments={"node_id": "login_button"},
            ),
            SimulatedTransition(
                action_tool_name="mobile.tap",
                from_screen_id="login_blank",
                to_screen_id="missing_password",
                match_arguments={"node_id": "login_button"},
            ),
            SimulatedTransition(
                action_tool_name="mobile.tap",
                from_screen_id="login_blank",
                to_screen_id="help",
                match_arguments={"node_id": "help_button"},
            ),
        ],
    )


def _request(
    scenario_id: str,
    *,
    goal: str,
    proposal: ExecutionProposal,
    success_text: str,
    blocked_conditions: list[str] | None = None,
) -> TaskHarnessRequest:
    return TaskHarnessRequest(
        goal=goal,
        target_kind=EntityKind.TASK,
        target_id=scenario_id,
        proposal=proposal,
        verification_spec=_verification_spec(scenario_id, success_text, blocked_conditions=blocked_conditions),
    )


def _proposal(suffix: str, action_tool_name: str, arguments: dict, scenario_id: str) -> ExecutionProposal:
    return ExecutionProposal(
        proposal_id=f"proposal:{scenario_id}:{suffix}",
        action_tool_name=action_tool_name,
        arguments=arguments,
        target_kind=EntityKind.TASK,
        target_id=scenario_id,
        rationale=f"Run simulated action {action_tool_name} for {scenario_id}.",
        expected_observation_changes=[action_tool_name],
        confidence=0.95,
    )


def _verification_spec(
    scenario_id: str,
    success_text: str,
    *,
    blocked_conditions: list[str] | None = None,
) -> VerificationSpec:
    check_id = success_text.casefold().replace(" ", "-")
    return VerificationSpec(
        verification_id=f"verification:{scenario_id}:{check_id}",
        target_kind=EntityKind.TASK,
        target_id=scenario_id,
        success_checks=[
            VerificationCheck(
                check_id=check_id,
                description=success_text,
                evidence_hint=success_text,
            )
        ],
        blocked_conditions=blocked_conditions or [],
    )


__all__ = [
    "approval_required_destructive_action_case",
    "dynamic_approval_required_destructive_action_case",
    "dynamic_fixed_script_contrast_case",
    "dynamic_login_success_case",
    "dynamic_recovery_retry_success_case",
    "dynamic_slow_loading_recovery_success_case",
    "handoff_followup_case",
    "login_success_case",
    "memory_blocks_wrong_success_case",
    "memory_guided_recovery_success_case",
    "memory_writeback_quality_rejects_unknown_case",
    "missing_password_blocked_case",
    "wrong_button_no_success_case",
]
