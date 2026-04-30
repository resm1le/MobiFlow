from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from enum import Enum
from pathlib import Path

from pydantic import Field

from mobiflow_agent.common.contracts import StrictModel
from mobiflow_agent.evaluation.scenario.baseline import (
    FixedScriptBaselineResult,
    FixedScriptBaselineRunner,
    FixedScriptStep,
)
from mobiflow_agent.evaluation.scenario.fixtures import (
    approval_required_destructive_action_case,
    dynamic_approval_required_destructive_action_case,
    dynamic_fixed_script_contrast_case,
    dynamic_login_success_case,
    dynamic_recovery_retry_success_case,
    dynamic_slow_loading_recovery_success_case,
    login_success_case,
    memory_blocks_wrong_success_case,
    memory_guided_recovery_success_case,
    memory_writeback_quality_rejects_unknown_case,
)
from mobiflow_agent.evaluation.scenario.models import ScenarioEvaluationCase, ScenarioEvaluationResult
from mobiflow_agent.evaluation.scenario.service import ScenarioEvaluationService, ScenarioMemoryEvaluationService
from mobiflow_agent.memory.runtime import TaskMemoryRuntime


class ScenarioRegressionGroup(str, Enum):
    NORMAL = "normal"
    RECOVERY = "recovery"
    APPROVAL = "approval"
    FIXED_SCRIPT_CONTRAST = "fixed_script_contrast"
    MEMORY = "memory"


class ScenarioRegressionCaseSpec(StrictModel):
    group: ScenarioRegressionGroup
    case: ScenarioEvaluationCase
    capability: str = Field(min_length=1)
    fixed_script_steps: list[FixedScriptStep] = Field(default_factory=list)
    compare_memory: bool = False


class ScenarioRegressionCaseResult(StrictModel):
    group: ScenarioRegressionGroup
    scenario_id: str = Field(min_length=1)
    capability: str = Field(min_length=1)
    matched: bool
    final_status: str
    verification_status: str | None = None
    entered_recovery: bool = False
    approval_pause: bool = False
    action_names: list[str] = Field(default_factory=list)
    memory_hit_count: int = 0
    memory_writeback_count: int = 0
    fixed_script_baseline: FixedScriptBaselineResult | None = None
    summary: str = Field(min_length=1)


class ScenarioRegressionReport(StrictModel):
    total_cases: int = 0
    matched_cases: int = 0
    mismatched_cases: int = 0
    results: list[ScenarioRegressionCaseResult] = Field(default_factory=list)
    summary: str = Field(min_length=1)


class ScenarioRegressionSuiteRunner:
    def __init__(
        self,
        *,
        evaluation_service: ScenarioEvaluationService | None = None,
        memory_runtime_factory: Callable[[], TaskMemoryRuntime] | None = None,
        baseline_runner: FixedScriptBaselineRunner | None = None,
    ) -> None:
        self._evaluation_service = evaluation_service or ScenarioEvaluationService()
        self._memory_runtime_factory = memory_runtime_factory
        self._baseline_runner = baseline_runner or FixedScriptBaselineRunner()

    def default_suite(self) -> list[ScenarioRegressionCaseSpec]:
        return [
            ScenarioRegressionCaseSpec(
                group=ScenarioRegressionGroup.NORMAL,
                capability="static_success_path",
                case=login_success_case(),
            ),
            ScenarioRegressionCaseSpec(
                group=ScenarioRegressionGroup.NORMAL,
                capability="dynamic_login_path",
                case=dynamic_login_success_case(),
            ),
            ScenarioRegressionCaseSpec(
                group=ScenarioRegressionGroup.RECOVERY,
                capability="dynamic_retry_recovery",
                case=dynamic_recovery_retry_success_case(),
            ),
            ScenarioRegressionCaseSpec(
                group=ScenarioRegressionGroup.RECOVERY,
                capability="slow_loading_recovery",
                case=dynamic_slow_loading_recovery_success_case(),
            ),
            ScenarioRegressionCaseSpec(
                group=ScenarioRegressionGroup.APPROVAL,
                capability="governed_destructive_action",
                case=approval_required_destructive_action_case(),
            ),
            ScenarioRegressionCaseSpec(
                group=ScenarioRegressionGroup.APPROVAL,
                capability="dynamic_governed_destructive_action",
                case=dynamic_approval_required_destructive_action_case(),
            ),
            ScenarioRegressionCaseSpec(
                group=ScenarioRegressionGroup.FIXED_SCRIPT_CONTRAST,
                capability="permission_popup_contrast",
                case=dynamic_fixed_script_contrast_case(),
                fixed_script_steps=[
                    FixedScriptStep(action_tool_name="mobile.launch", arguments={"app": "demo"}),
                    FixedScriptStep(action_tool_name="mobile.input_text", arguments={"node_id": "username", "text": "alice"}),
                    FixedScriptStep(action_tool_name="mobile.input_text", arguments={"node_id": "password", "text": "secret"}),
                    FixedScriptStep(action_tool_name="mobile.tap", arguments={"node_id": "login_button"}),
                ],
            ),
            ScenarioRegressionCaseSpec(
                group=ScenarioRegressionGroup.MEMORY,
                capability="memory_guided_recovery",
                case=memory_guided_recovery_success_case(),
                compare_memory=True,
            ),
            ScenarioRegressionCaseSpec(
                group=ScenarioRegressionGroup.MEMORY,
                capability="memory_blocks_wrong_success",
                case=memory_blocks_wrong_success_case(),
                compare_memory=True,
            ),
            ScenarioRegressionCaseSpec(
                group=ScenarioRegressionGroup.MEMORY,
                capability="unknown_writeback_governance",
                case=memory_writeback_quality_rejects_unknown_case(),
                compare_memory=True,
            ),
        ]

    def run_default_suite(self) -> ScenarioRegressionReport:
        return self.run_suite(self.default_suite())

    def run_suite(self, specs: list[ScenarioRegressionCaseSpec]) -> ScenarioRegressionReport:
        results = [self.run_spec(spec) for spec in specs]
        matched_cases = sum(1 for result in results if result.matched)
        total_cases = len(results)
        return ScenarioRegressionReport(
            total_cases=total_cases,
            matched_cases=matched_cases,
            mismatched_cases=total_cases - matched_cases,
            results=results,
            summary=(
                f"Scenario regression suite completed: "
                f"{matched_cases}/{total_cases} matched, {total_cases - matched_cases} mismatched."
            ),
        )

    def run_spec(self, spec: ScenarioRegressionCaseSpec) -> ScenarioRegressionCaseResult:
        evaluation_result = self._evaluation_service.run_case(spec.case)
        memory_hit_count = 0
        memory_writeback_count = 0
        if spec.compare_memory and self._memory_runtime_factory is not None:
            memory_result = ScenarioMemoryEvaluationService(
                memory_runtime_factory=self._memory_runtime_factory,
            ).compare_case(spec.case)
            memory_hit_count = memory_result.memory_hit_count
            memory_writeback_count = memory_result.writeback_count
        fixed_script_baseline = None
        if spec.fixed_script_steps:
            fixed_script_baseline = self._baseline_runner.run(spec.case.platform_scenario, spec.fixed_script_steps)
        return self._case_result(
            spec=spec,
            evaluation_result=evaluation_result,
            memory_hit_count=memory_hit_count,
            memory_writeback_count=memory_writeback_count,
            fixed_script_baseline=fixed_script_baseline,
        )

    def export_json(self, report: ScenarioRegressionReport) -> dict:
        return report.model_dump(mode="json")

    def export_markdown(self, report: ScenarioRegressionReport) -> str:
        lines = [
            "# Scenario Regression Report",
            "",
            report.summary,
            "",
            f"- Total cases: {report.total_cases}",
            f"- Matched cases: {report.matched_cases}",
            f"- Mismatched cases: {report.mismatched_cases}",
            "",
        ]
        for group in ScenarioRegressionGroup:
            group_results = [result for result in report.results if result.group == group]
            if not group_results:
                continue
            lines.extend([f"## {group.value}", ""])
            for result in group_results:
                lines.append(
                    f"- {result.scenario_id} ({result.capability}): "
                    f"matched={result.matched}, final={result.final_status}, "
                    f"verification={result.verification_status or 'none'}"
                )
                lines.append(
                    f"  actions={', '.join(result.action_names) or 'none'}, "
                    f"recovery={result.entered_recovery}, approval={result.approval_pause}, "
                    f"memory_hits={result.memory_hit_count}, memory_writeback={result.memory_writeback_count}"
                )
                if result.fixed_script_baseline is not None:
                    baseline = result.fixed_script_baseline
                    lines.append(
                        f"  fixed_script: completed={baseline.completed}, "
                        f"final_screen={baseline.final_screen_id}, failed_step={baseline.failed_step_index}"
                    )
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def write_json(self, report: ScenarioRegressionReport, path: str | Path) -> Path:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(self.export_json(report), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return output_path

    def write_markdown(self, report: ScenarioRegressionReport, path: str | Path) -> Path:
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(self.export_markdown(report), encoding="utf-8")
        return output_path

    @staticmethod
    def _case_result(
        *,
        spec: ScenarioRegressionCaseSpec,
        evaluation_result: ScenarioEvaluationResult,
        memory_hit_count: int,
        memory_writeback_count: int,
        fixed_script_baseline: FixedScriptBaselineResult | None,
    ) -> ScenarioRegressionCaseResult:
        final_response = evaluation_result.final_response
        verdict = final_response.latest_verdict
        action_names = [trace.action_tool_name for trace in evaluation_result.action_traces]
        return ScenarioRegressionCaseResult(
            group=spec.group,
            scenario_id=spec.case.scenario_id,
            capability=spec.capability,
            matched=evaluation_result.matched,
            final_status=final_response.status.value,
            verification_status=verdict.status.value if verdict is not None else None,
            entered_recovery=any(response.status.value in {"scheduled", "handed_off"} for response in evaluation_result.responses)
            or bool(verdict and verdict.diagnostics.get("suggested_recovery_direction") == "recover_or_handoff"),
            approval_pause=any(response.status.value == "awaiting_approval" for response in evaluation_result.responses),
            action_names=action_names,
            memory_hit_count=memory_hit_count,
            memory_writeback_count=memory_writeback_count,
            fixed_script_baseline=fixed_script_baseline,
            summary=(
                f"{spec.group.value}/{spec.capability}: final={final_response.status.value}, "
                f"verification={verdict.status.value if verdict is not None else 'none'}, "
                f"matched={evaluation_result.matched}."
            ),
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the MobiFlow Agent scenario regression suite.")
    parser.add_argument("--format", choices=["json", "markdown"], default="markdown")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    runner = ScenarioRegressionSuiteRunner()
    report = runner.run_default_suite()
    if args.output is not None:
        if args.format == "json":
            runner.write_json(report, args.output)
        else:
            runner.write_markdown(report, args.output)
    else:
        if args.format == "json":
            print(json.dumps(runner.export_json(report), ensure_ascii=False, indent=2))
        else:
            print(runner.export_markdown(report))
    return 0 if report.mismatched_cases == 0 else 1


__all__ = [
    "main",
    "ScenarioRegressionCaseResult",
    "ScenarioRegressionCaseSpec",
    "ScenarioRegressionGroup",
    "ScenarioRegressionReport",
    "ScenarioRegressionSuiteRunner",
]


if __name__ == "__main__":
    raise SystemExit(main())
