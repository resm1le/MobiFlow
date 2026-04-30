from __future__ import annotations

from typing import Any

from pydantic import Field

from mobiflow_agent.common.contracts import EntityKind, ExecutionProposal, StrictModel
from mobiflow_agent.platform.simulation import SimulatedActionTrace, SimulatedMobilePlatformAdapter, SimulatedMobileScenario
from mobiflow_agent.platform.types import GovernedActionState
from mobiflow_agent.runtime.state import CallerContext


class FixedScriptStep(StrictModel):
    action_tool_name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


class FixedScriptBaselineResult(StrictModel):
    scenario_id: str = Field(min_length=1)
    completed: bool
    failed_step_index: int | None = None
    final_screen_id: str = Field(min_length=1)
    action_traces: list[SimulatedActionTrace] = Field(default_factory=list)
    summary: str = Field(min_length=1)


class FixedScriptBaselineRunner:
    def run(self, scenario: SimulatedMobileScenario, steps: list[FixedScriptStep]) -> FixedScriptBaselineResult:
        adapter = SimulatedMobilePlatformAdapter(scenario, target_id=scenario.scenario_id)
        failed_step_index: int | None = None
        for index, step in enumerate(steps):
            proposal = ExecutionProposal(
                proposal_id=f"fixed-script:{scenario.scenario_id}:{index + 1}",
                action_tool_name=step.action_tool_name,
                arguments=step.arguments,
                target_kind=EntityKind.TASK,
                target_id=scenario.scenario_id,
                rationale="Fixed script baseline action.",
            )
            result = adapter.submit_execution_proposal(
                proposal,
                CallerContext(
                    session_id=f"fixed-script:{scenario.scenario_id}",
                    agent_task_id=scenario.scenario_id,
                    turn_id=f"turn:{index + 1}",
                    step_id=f"step:{index + 1}",
                ),
            )
            if result.state != GovernedActionState.EXECUTED:
                failed_step_index = index
                break
        completed = failed_step_index is None
        return FixedScriptBaselineResult(
            scenario_id=scenario.scenario_id,
            completed=completed,
            failed_step_index=failed_step_index,
            final_screen_id=adapter.current_screen_id,
            action_traces=adapter.action_traces,
            summary=(
                f"Fixed script completed {len(steps)} step(s)."
                if completed
                else f"Fixed script failed at step index {failed_step_index} on screen {adapter.current_screen_id}."
            ),
        )


__all__ = ["FixedScriptBaselineResult", "FixedScriptBaselineRunner", "FixedScriptStep"]
