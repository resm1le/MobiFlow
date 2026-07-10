from __future__ import annotations

from typing import Any

from mobiflow_agent.agents.contracts import AgentRole
from mobiflow_agent.model.runtime import ModelRuntime

from .models import TaskIntakeResult, TaskIntakeSpec, TaskIntakeStatus, TestCase
from .prompting import TaskInterpreterPromptBuilder, TestCaseParserPromptBuilder
from .templates import ScenarioTemplate, ScenarioTemplateRegistry


class TaskInterpreter:
    def __init__(
        self,
        *,
        model_runtime: ModelRuntime | None = None,
        prompt_builder: TaskInterpreterPromptBuilder | None = None,
        template_registry: ScenarioTemplateRegistry | None = None,
    ) -> None:
        self._model_runtime = model_runtime
        self._prompt_builder = prompt_builder or TaskInterpreterPromptBuilder()
        self._template_registry = template_registry or ScenarioTemplateRegistry.default()

    def interpret(
        self,
        raw_goal: str,
        *,
        platform_context: dict[str, Any] | None = None,
        profile_name: str | None = None,
    ) -> TaskIntakeResult:
        if self._model_runtime is not None:
            model_result = self._interpret_with_model(raw_goal, platform_context=platform_context, profile_name=profile_name)
            if model_result is not None:
                return model_result
        spec = self._fallback_spec(raw_goal)
        status = TaskIntakeStatus.READY if not spec.missing_fields else TaskIntakeStatus.NEEDS_CLARIFICATION
        return TaskIntakeResult(
            status=status,
            spec=spec,
            clarification_questions=self._clarification_questions(spec),
            issues=list(spec.missing_fields),
        )

    def _interpret_with_model(
        self,
        raw_goal: str,
        *,
        platform_context: dict[str, Any] | None,
        profile_name: str | None,
    ) -> TaskIntakeResult | None:
        prompt = self._prompt_builder.build(
            raw_goal=raw_goal,
            scenario_templates=self._template_registry.visible_templates(),
            platform_context=platform_context or {},
        )
        try:
            generated = self._model_runtime.generate_structured(
                role=AgentRole.TASK_INTERPRETER,
                prompt=prompt,
                response_model=TaskIntakeSpec,
                profile_name=profile_name,
                metadata={"raw_goal": raw_goal},
            )
        except Exception:
            return None
        return TaskIntakeResult(
            status=TaskIntakeStatus.READY,
            spec=generated.output,
            trace_refs=[generated.response.trace.invocation_id],
        )

    def _fallback_spec(self, raw_goal: str) -> TaskIntakeSpec:
        template = self._template_registry.match(raw_goal)
        if template is None:
            return TaskIntakeSpec(
                raw_goal=raw_goal,
                normalized_goal=raw_goal,
                missing_fields=["scenario_id"],
                confidence=0.0,
                needs_confirmation=True,
            )
        return self._spec_from_template(raw_goal, template)

    @staticmethod
    def _spec_from_template(raw_goal: str, template: ScenarioTemplate) -> TaskIntakeSpec:
        return TaskIntakeSpec(
            raw_goal=raw_goal,
            normalized_goal=template.normalized_goal,
            intent=template.intent,
            scenario_id=template.scenario_id,
            target_kind=template.target_kind,
            target_id=template.target_id,
            verification_template=template.verification_template,
            verification_params=dict(template.verification_params),
            allowed_actions=list(template.allowed_actions),
            approval_mode=template.approval_mode,
            confidence=0.75,
            needs_confirmation=template.needs_confirmation,
            risk_flags=list(template.risk_flags),
        )

    @staticmethod
    def _clarification_questions(spec: TaskIntakeSpec) -> list[str]:
        questions = []
        if "scenario_id" in spec.missing_fields:
            questions.append("需要明确要运行的移动实验场景。")
        if spec.needs_confirmation and spec.risk_flags:
            questions.append("该任务包含高风险操作，需要显式确认后才能创建执行 session。")
        return questions


class TestCaseParser:
    def __init__(
        self,
        *,
        model_runtime: ModelRuntime | None = None,
        prompt_builder: TestCaseParserPromptBuilder | None = None,
        template_registry: ScenarioTemplateRegistry | None = None,
    ) -> None:
        self._model_runtime = model_runtime
        self._prompt_builder = prompt_builder or TestCaseParserPromptBuilder()
        self._template_registry = template_registry or ScenarioTemplateRegistry.default()

    def parse(
        self,
        raw_goal: str,
        *,
        platform_context: dict[str, Any] | None = None,
        profile_name: str | None = None,
    ) -> TaskIntakeResult:
        if self._model_runtime is None:
            return self._clarification("需要模型运行时来把自然语言目标编译成 TestCase。")
        prompt = self._prompt_builder.build(
            raw_goal=raw_goal,
            scenario_templates=self._template_registry.visible_templates(),
            platform_context=platform_context or {},
        )
        try:
            generated = self._model_runtime.generate_structured(
                role=AgentRole.TASK_INTERPRETER,
                prompt=prompt,
                response_model=TestCase,
                profile_name=profile_name,
                metadata={"raw_goal": raw_goal},
            )
        except Exception:
            return self._clarification("无法把该目标解析为 TestCase，请补充更明确的描述。")
        return TaskIntakeResult(
            status=TaskIntakeStatus.READY,
            test_case=generated.output,
            trace_refs=[generated.response.trace.invocation_id],
        )

    @staticmethod
    def _clarification(question: str) -> TaskIntakeResult:
        return TaskIntakeResult(
            status=TaskIntakeStatus.NEEDS_CLARIFICATION,
            clarification_questions=[question],
        )


__all__ = ["TaskInterpreter", "TestCaseParser"]
