from __future__ import annotations

from mobiflow_agent.agents.contracts import AgentRole
from mobiflow_agent.collection.models import (
    CollectionDispatchStatus,
    CollectionIntent,
    IntentPlannerDecision,
    IntentPlannerDecisionType,
    IntentPlanningResult,
)
from mobiflow_agent.collection.prompting import IntentPlannerPromptBuilder
from mobiflow_agent.model.runtime import ModelRuntime
from mobiflow_agent.platform.types import (
    DispatchDeviceContext,
    RunPlanningCatalogContext,
)
from mobiflow_agent.waypoint.catalog import SequenceCatalog


class IntentPlanner:
    def __init__(
        self,
        *,
        model_runtime: ModelRuntime | None = None,
        prompt_builder: IntentPlannerPromptBuilder | None = None,
        profile_name: str | None = None,
    ) -> None:
        self._model_runtime = model_runtime
        self._prompt_builder = prompt_builder or IntentPlannerPromptBuilder()
        self._profile_name = profile_name

    def plan(
        self,
        intent: CollectionIntent,
        *,
        sequence_catalog: SequenceCatalog,
        devices: list[DispatchDeviceContext],
        planning_catalog: RunPlanningCatalogContext,
        profile_name: str | None = None,
    ) -> IntentPlanningResult:
        if self._model_runtime is None:
            return self._clarification(
                "intent_planner_model_runtime_missing",
                "需要模型运行时来解析采集意图；请提供明确的 sequence、数量和设备条件。",
            )
        prompt = self._prompt_builder.build(
            intent=intent,
            sequences=sequence_catalog.list_sequences(),
            devices=devices,
            planning_catalog=planning_catalog,
        )
        try:
            generated = self._model_runtime.generate_structured(
                role=AgentRole.PLANNER,
                prompt=prompt,
                response_model=IntentPlannerDecision,
                profile_name=profile_name or self._profile_name,
                metadata={
                    "task_type": intent.task_type,
                    "sequence_count": len(sequence_catalog.list_sequences()),
                    "device_count": len(devices),
                },
            )
        except Exception:
            return self._clarification(
                "intent_planner_model_error",
                "无法可靠解析采集意图；请明确 sequence、每组设备数量或具体设备 ID。",
            )

        decision = generated.output
        trace_refs = [generated.response.trace.invocation_id]
        if decision.decision_type == IntentPlannerDecisionType.CLARIFY:
            return IntentPlanningResult(
                status=CollectionDispatchStatus.NEEDS_CLARIFICATION,
                confidence=decision.confidence,
                clarification_questions=list(decision.clarification_questions),
                trace_refs=trace_refs,
            )
        return IntentPlanningResult(
            status=CollectionDispatchStatus.PLANNED,
            plan=decision.plan,
            confidence=decision.confidence,
            trace_refs=trace_refs,
        )

    @staticmethod
    def _clarification(issue: str, question: str) -> IntentPlanningResult:
        return IntentPlanningResult(
            status=CollectionDispatchStatus.NEEDS_CLARIFICATION,
            issues=[issue],
            clarification_questions=[question],
        )


__all__ = ["IntentPlanner"]
