from __future__ import annotations

from mobiflow_agent.common.contracts import EntityKind

from .models import TaskIntakeSpec, TaskIntakeValidationResult, TestCase
from .templates import DEFAULT_MOBILE_ACTIONS, ScenarioTemplateRegistry


class TaskIntakeValidator:
    def __init__(self, *, template_registry: ScenarioTemplateRegistry | None = None) -> None:
        self._template_registry = template_registry or ScenarioTemplateRegistry.default()

    def validate(self, spec: TaskIntakeSpec, *, confirmed: bool = False) -> TaskIntakeValidationResult:
        issues = list(spec.missing_fields)
        questions: list[str] = []
        template = self._template_registry.get(spec.scenario_id)
        if template is None:
            issues.append("unknown_scenario_id")
            questions.append("Please choose a registered scenario template.")
        else:
            if spec.target_kind != EntityKind.TASK:
                issues.append("invalid_target_kind")
            if spec.target_id != template.target_id:
                issues.append("target_id_mismatch")
            if spec.verification_template != template.verification_template:
                issues.append("verification_template_mismatch")

        if not self._template_registry.has_verification_template(spec.verification_template):
            issues.append("unknown_verification_template")

        allowed_actions = self._template_registry.allowed_actions
        for action in spec.allowed_actions:
            if action not in allowed_actions:
                issues.append(f"disallowed_action:{action}")

        if spec.risk_flags and spec.needs_confirmation and not confirmed:
            issues.append("confirmation_required")
            questions.append("Please confirm whether this high-risk task is allowed.")

        normalized_issues = self._dedupe(issues)
        return TaskIntakeValidationResult(
            accepted=not normalized_issues,
            issues=normalized_issues,
            clarification_questions=self._dedupe(questions),
        )

    @staticmethod
    def _dedupe(values: list[str]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            deduped.append(value)
        return deduped


class TestCaseValidator:
    def __init__(self, *, allowed_actions: set[str] | None = None) -> None:
        self._allowed_actions = allowed_actions or set(DEFAULT_MOBILE_ACTIONS)

    def validate(self, test_case: TestCase, *, confirmed: bool = False) -> TaskIntakeValidationResult:
        issues: list[str] = []
        questions: list[str] = []

        if not test_case.normalized_goal.strip():
            issues.append("missing_normalized_goal")
        if not test_case.expected_outcomes:
            issues.append("missing_expected_outcome")
            questions.append("这个测试用例的预期结果是什么？")

        for step in test_case.steps:
            if step.hint_action is not None and step.hint_action not in self._allowed_actions:
                issues.append(f"disallowed_action:{step.hint_action}")

        if test_case.risk_flags and test_case.needs_confirmation and not confirmed:
            issues.append("confirmation_required")
            questions.append("该用例包含高风险操作，需要显式确认后才能创建执行 session。")

        normalized_issues = self._dedupe(issues)
        return TaskIntakeValidationResult(
            accepted=not normalized_issues,
            issues=normalized_issues,
            clarification_questions=self._dedupe(questions),
        )

    @staticmethod
    def _dedupe(values: list[str]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            deduped.append(value)
        return deduped


__all__ = ["TaskIntakeValidator", "TestCaseValidator"]
