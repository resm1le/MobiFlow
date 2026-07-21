from mobiflow_agent.common.contracts import DEFAULT_MOBILE_ACTIONS


def test_default_mobile_actions_value():
    assert DEFAULT_MOBILE_ACTIONS == (
        "mobile.launch",
        "mobile.tap",
        "mobile.input_text",
        "mobile.wait",
        "mobile.back",
    )
    assert not hasattr(DEFAULT_MOBILE_ACTIONS, "append")


def test_templates_and_planner_reference_common_constant():
    from mobiflow_agent.agents.planner import PlannerAgent
    from mobiflow_agent.intake.templates import DEFAULT_MOBILE_ACTIONS as TEMPLATES_ACTIONS

    assert TEMPLATES_ACTIONS is DEFAULT_MOBILE_ACTIONS
    assert PlannerAgent.DEFAULT_DYNAMIC_SIDE_EFFECTS is DEFAULT_MOBILE_ACTIONS
    assert not hasattr(PlannerAgent.DEFAULT_DYNAMIC_SIDE_EFFECTS, "append")


def test_scenario_template_action_defaults_are_isolated():
    from mobiflow_agent.intake.templates import ScenarioTemplate

    first = ScenarioTemplate(
        scenario_id="first",
        intent="first",
        normalized_goal="First goal.",
        target_id="first",
        verification_template="first",
    )
    second = ScenarioTemplate(
        scenario_id="second",
        intent="second",
        normalized_goal="Second goal.",
        target_id="second",
        verification_template="second",
    )

    first.allowed_actions.append("mobile.first_only")

    assert "mobile.first_only" not in second.allowed_actions
    assert "mobile.first_only" not in DEFAULT_MOBILE_ACTIONS
