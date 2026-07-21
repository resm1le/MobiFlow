from mobiflow_agent.common.contracts import DEFAULT_MOBILE_ACTIONS


def test_default_mobile_actions_value():
    assert DEFAULT_MOBILE_ACTIONS == [
        "mobile.launch",
        "mobile.tap",
        "mobile.input_text",
        "mobile.wait",
        "mobile.back",
    ]


def test_templates_and_planner_reference_common_constant():
    from mobiflow_agent.agents.planner import PlannerAgent
    from mobiflow_agent.intake.templates import DEFAULT_MOBILE_ACTIONS as TEMPLATES_ACTIONS

    assert TEMPLATES_ACTIONS == DEFAULT_MOBILE_ACTIONS
    assert PlannerAgent.DEFAULT_DYNAMIC_SIDE_EFFECTS == DEFAULT_MOBILE_ACTIONS
