from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from mobiflow_agent.common.contracts import StrictModel
from mobiflow_agent.platform.types import GovernedActionState


class SimulatedUiNode(StrictModel):
    node_id: str = Field(min_length=1)
    role: str = Field(default="text", min_length=1)
    text: str | None = None
    value: str | None = None
    content_description: str | None = None
    enabled: bool = True
    visible: bool = True
    children: list[SimulatedUiNode] = Field(default_factory=list)

    def as_tree(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "role": self.role,
            "text": self.text,
            "value": self.value,
            "content_description": self.content_description,
            "enabled": self.enabled,
            "visible": self.visible,
            "children": [child.as_tree() for child in self.children],
        }


class SimulatedScreen(StrictModel):
    screen_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    nodes: list[SimulatedUiNode] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    blocked_reason: str | None = None

    def as_snapshot(self) -> dict[str, Any]:
        return {
            "screen_id": self.screen_id,
            "title": self.title,
            "metadata": self.metadata,
            "blocked_reason": self.blocked_reason,
            "ui_tree": [node.as_tree() for node in self.nodes],
        }


class SimulatedTransition(StrictModel):
    action_tool_name: str = Field(min_length=1)
    from_screen_id: str = Field(min_length=1)
    to_screen_id: str = Field(min_length=1)
    match_arguments: dict[str, Any] = Field(default_factory=dict)
    requires_approval: bool = False
    confirmation_summary: str | None = None
    result: dict[str, Any] = Field(default_factory=dict)
    summary: str | None = None

    def matches(self, *, action_tool_name: str, from_screen_id: str, arguments: dict[str, Any]) -> bool:
        if self.action_tool_name != action_tool_name or self.from_screen_id != from_screen_id:
            return False
        for key, expected_value in self.match_arguments.items():
            if arguments.get(key) != expected_value:
                return False
        return True


class SimulatedMobileScenario(StrictModel):
    scenario_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    initial_screen_id: str = Field(min_length=1)
    screens: dict[str, SimulatedScreen] = Field(default_factory=dict)
    transitions: list[SimulatedTransition] = Field(default_factory=list)
    resources: dict[str, dict[str, Any] | str | bytes] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_graph(self) -> "SimulatedMobileScenario":
        if self.initial_screen_id not in self.screens:
            raise ValueError("SimulatedMobileScenario initial_screen_id must reference a screen.")
        for transition in self.transitions:
            if transition.from_screen_id not in self.screens:
                raise ValueError(f"Transition references unknown from_screen_id: {transition.from_screen_id}.")
            if transition.to_screen_id not in self.screens:
                raise ValueError(f"Transition references unknown to_screen_id: {transition.to_screen_id}.")
        return self


class SimulatedActionTrace(StrictModel):
    sequence: int = Field(ge=1)
    proposal_id: str = Field(min_length=1)
    action_tool_name: str = Field(min_length=1)
    from_screen_id: str = Field(min_length=1)
    to_screen_id: str | None = None
    state: GovernedActionState
    audit_id: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)
    requires_approval: bool = False
    approved: bool | None = None
    error_code: str | None = None
    summary: str = Field(min_length=1)


__all__ = [
    "SimulatedActionTrace",
    "SimulatedMobileScenario",
    "SimulatedScreen",
    "SimulatedTransition",
    "SimulatedUiNode",
]
