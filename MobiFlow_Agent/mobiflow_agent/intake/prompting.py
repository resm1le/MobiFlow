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


class TestCaseParserPromptBuilder:
    def build(
        self,
        *,
        raw_goal: str,
        scenario_templates: list[dict],
        platform_context: dict[str, Any] | None = None,
    ) -> PromptBundle:
        return PromptBundle(
            system_prompt=(
                "You are the TestCase compiler for MobiFlow Agent. Convert the raw mobile "
                "regression goal into a structured TestCase: a normalized_goal, optional steps, "
                "and one or more expected_outcomes describing what must be observed to pass. "
                "The provided scenario_templates are few-shot examples only, not a closed list; "
                "if none match, still produce a faithful TestCase. Do not invent devices or actions "
                "outside the platform_context. Return only the structured TestCase."
            ),
            context_payload={
                "raw_goal": raw_goal,
                "scenario_templates": scenario_templates,
                "platform_context": platform_context or {},
            },
            preserve_keys=["raw_goal", "scenario_templates", "platform_context"],
            metadata={"prompt_kind": "testcase_parser"},
        )


class AssertionSynthesizerPromptBuilder:
    def build(
        self,
        *,
        outcome_text: str,
        allowed_fact_ids: list[str],
        allowed_operators: list[str],
        violation: str | None = None,
    ) -> PromptBundle:
        return PromptBundle(
            system_prompt=(
                "You synthesize a single verification check for one expected outcome of a mobile "
                "regression test. Emit at least one structured predicate. Each predicate.operator MUST "
                "be one of allowed_operators; each predicate.fact_id MUST be one of allowed_fact_ids; "
                "field_path must be non-empty (e.g. 'value.title' or 'value[].node_id'). For a "
                "not_exists predicate, anchor fact_id to a screen fact that is reliably observed so "
                "you test 'absent on a screen we DID observe'. evidence_hint is human context only and "
                "must never be the sole matcher. Return only the structured assertion."
            ),
            context_payload={
                "outcome_text": outcome_text,
                "allowed_fact_ids": allowed_fact_ids,
                "allowed_operators": allowed_operators,
                "previous_violation": violation or "",
            },
            preserve_keys=["outcome_text", "allowed_fact_ids", "allowed_operators", "previous_violation"],
            metadata={"prompt_kind": "assertion_synthesizer"},
        )


__all__ = ["AssertionSynthesizerPromptBuilder", "TaskInterpreterPromptBuilder", "TestCaseParserPromptBuilder"]
