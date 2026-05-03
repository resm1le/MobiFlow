from __future__ import annotations

from typing import Any

from mobiflow_agent.model.prompting import PromptBundle


class TaskInterpreterPromptBuilder:
    def build(
        self,
        *,
        raw_goal: str,
        scenario_templates: list[dict],
        platform_context: dict[str, Any] | None = None,
    ) -> PromptBundle:
        return PromptBundle(
            system_prompt=(
                "You are the task intake interpreter for MobiFlow Agent. "
                "Return only a structured TaskIntakeSpec candidate. Do not call tools and do not invent "
                "scenario ids, target ids, verification templates, devices, or actions outside the provided context."
            ),
            context_payload={
                "raw_goal": raw_goal,
                "scenario_templates": scenario_templates,
                "platform_context": platform_context or {},
            },
            preserve_keys=["raw_goal", "scenario_templates", "platform_context"],
            metadata={"prompt_kind": "task_interpreter"},
        )


__all__ = ["TaskInterpreterPromptBuilder"]
