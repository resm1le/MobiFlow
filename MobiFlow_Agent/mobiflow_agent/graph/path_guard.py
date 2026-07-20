"""路径约束守卫:判定动态步提出的动作是否偏离标准路径。

纯函数,无副作用。数据源与现有惯例一致:当前屏幕取自
`mobile_observation_summary` 观察事实的 `screen_id`(硬编码字面量,
与 step_policy.py/verifier.py 一致,避免 graph 层依赖 simulation 层)。
"""

from __future__ import annotations

from mobiflow_agent.common.contracts import ExecutionProposal, ObservationView
from mobiflow_agent.task.plan import TaskStep

OFF_STANDARD_PATH = "off_standard_path"

_MOBILE_OBSERVATION_SUMMARY_FACT_ID = "mobile_observation_summary"


def _current_screen_id(observation: ObservationView | None) -> str | None:
    if observation is None:
        return None
    for fact in observation.facts:
        if fact.fact_id == _MOBILE_OBSERVATION_SUMMARY_FACT_ID and isinstance(fact.value, dict):
            return fact.value.get("screen_id")
    return None


def evaluate_path_constraint(
    step: TaskStep,
    observation: ObservationView | None,
    proposal: ExecutionProposal,
) -> str | None:
    """返回违规原因字符串(越界),或 None(符合标准路径 / 无约束)。"""
    constraint = step.path_constraint
    if constraint is None:
        return None

    if constraint.forbidden_actions and proposal.action_tool_name in constraint.forbidden_actions:
        return (
            f"Proposed action '{proposal.action_tool_name}' is forbidden by the "
            f"path constraint for waypoint '{step.step_id}'."
        )

    if constraint.required_screens:
        screen_id = _current_screen_id(observation)
        if screen_id is None:
            return (
                f"Cannot confirm the current screen for waypoint '{step.step_id}'; "
                f"required one of {constraint.required_screens}."
            )
        if screen_id not in constraint.required_screens:
            return (
                f"Current screen '{screen_id}' is outside the standard path for "
                f"waypoint '{step.step_id}' (required one of {constraint.required_screens})."
            )

    return None
