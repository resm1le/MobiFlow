from __future__ import annotations

from typing import Callable

from mobiflow_agent.agents import ExecutorAgent, ObserverAgent
from mobiflow_agent.control import TaskControlPolicy
from mobiflow_agent.graph import TaskGraphRuntime
from mobiflow_agent.memory.models import TaskMemoryRecordStatus
from mobiflow_agent.memory.runtime import TaskMemoryRuntime
from mobiflow_agent.evaluation.scenario.models import (
    ScenarioEvaluationCase,
    ScenarioEvaluationReport,
    ScenarioEvaluationResult,
    ScenarioMemoryComparisonOutcome,
    ScenarioMemoryComparisonReport,
    ScenarioMemoryComparisonResult,
)
from mobiflow_agent.evaluation.scenario.quality_gate import ScenarioQualityGate
from mobiflow_agent.platform.simulation import SimulatedMobilePlatformAdapter
from mobiflow_agent.runtime.harness import InMemoryTaskHarnessStore, TaskHarnessService, TaskHeartbeatRunner, TaskHarnessStatus


class ScenarioEvaluationService:
    def __init__(
        self,
        *,
        quality_gate: ScenarioQualityGate | None = None,
        memory_runtime_factory: Callable[[], TaskMemoryRuntime] | None = None,
    ) -> None:
        self._quality_gate = quality_gate or ScenarioQualityGate()
        self._memory_runtime_factory = memory_runtime_factory

    def run_case(self, case: ScenarioEvaluationCase) -> ScenarioEvaluationResult:
        adapter = SimulatedMobilePlatformAdapter(
            case.platform_scenario,
            target_id=case.scenario_id,
        )
        memory_runtime = self._memory_runtime_factory() if self._memory_runtime_factory is not None else None
        orchestrator = TaskGraphRuntime(
            observer_agent=ObserverAgent(adapter=adapter),
            executor_agent=ExecutorAgent(adapter),
            policy=TaskControlPolicy(allow_recovery=case.allow_recovery),
            memory_runtime=memory_runtime,
        )
        harness = TaskHarnessService(
            orchestrator=orchestrator,
            store=InMemoryTaskHarnessStore(),
        )

        responses = []
        heartbeat = TaskHeartbeatRunner(harness)
        for index, request in enumerate(case.requests):
            response = harness.start(request)
            responses.append(response)
            if response.status == TaskHarnessStatus.AWAITING_APPROVAL and index in case.approval_decisions:
                response = harness.resume_approval(response.job_id, approved=case.approval_decisions[index])
                responses.append(response)
            for _ in range(case.heartbeat_ticks):
                if response.status != TaskHarnessStatus.SCHEDULED:
                    break
                tick_responses = heartbeat.run_once(now_ms=response.next_wakeup_at or 0)
                if not tick_responses:
                    break
                responses.extend(tick_responses)
                response = tick_responses[-1]

        result = ScenarioEvaluationResult(
            scenario_id=case.scenario_id,
            name=case.name,
            responses=responses,
            final_response=responses[-1],
            action_traces=adapter.action_traces,
            matched=False,
            failures=[],
            summary=f"Scenario {case.name} executed and is awaiting quality gate evaluation.",
        )
        return self._quality_gate.evaluate(case, result)

    def run_cases(self, cases: list[ScenarioEvaluationCase]) -> ScenarioEvaluationReport:
        results = [self.run_case(case) for case in cases]
        matched_cases = sum(1 for result in results if result.matched)
        total_cases = len(results)
        mismatched_cases = total_cases - matched_cases
        return ScenarioEvaluationReport(
            total_cases=total_cases,
            matched_cases=matched_cases,
            mismatched_cases=mismatched_cases,
            results=results,
            summary=(
                f"Scenario evaluation completed: "
                f"{matched_cases}/{total_cases} matched, {mismatched_cases} mismatched."
            ),
        )


class ScenarioMemoryEvaluationService:
    def __init__(
        self,
        *,
        memory_runtime_factory: Callable[[], TaskMemoryRuntime],
        quality_gate: ScenarioQualityGate | None = None,
    ) -> None:
        self._memory_runtime_factory = memory_runtime_factory
        self._quality_gate = quality_gate or ScenarioQualityGate()

    def compare_case(self, case: ScenarioEvaluationCase) -> ScenarioMemoryComparisonResult:
        memory_off_result = ScenarioEvaluationService(quality_gate=self._quality_gate).run_case(case)
        memory_runtime = self._memory_runtime_factory()
        memory_on_result = ScenarioEvaluationService(
            quality_gate=self._quality_gate,
            memory_runtime_factory=lambda: memory_runtime,
        ).run_case(case)
        memory_hit_count = sum(len(context.matches) for context in memory_runtime.retrieval_contexts())
        active_hit_count = sum(
            1
            for context in memory_runtime.retrieval_contexts()
            for match in context.matches
            if match.record.status == TaskMemoryRecordStatus.ACTIVE
        )
        writeback_results = memory_runtime.writeback_results()
        writeback_count = sum(len(result.stored_records) for result in writeback_results)
        quality_rejection_count = sum(result.rejected_count for result in writeback_results)
        quarantined_count = sum(result.quarantined_count for result in writeback_results)
        expired_count = sum(result.expired_count for result in writeback_results)
        superseded_count = sum(result.superseded_count for result in writeback_results)
        outcome = self._comparison_outcome(
            memory_off_result=memory_off_result,
            memory_on_result=memory_on_result,
        )
        return ScenarioMemoryComparisonResult(
            scenario_id=case.scenario_id,
            name=case.name,
            memory_off_result=memory_off_result,
            memory_on_result=memory_on_result,
            outcome=outcome,
            improved=outcome == ScenarioMemoryComparisonOutcome.IMPROVED,
            regressed=outcome == ScenarioMemoryComparisonOutcome.REGRESSED,
            unchanged=outcome == ScenarioMemoryComparisonOutcome.UNCHANGED,
            memory_hit_count=memory_hit_count,
            active_hit_count=active_hit_count,
            writeback_count=writeback_count,
            quality_rejection_count=quality_rejection_count,
            quarantined_count=quarantined_count,
            expired_count=expired_count,
            superseded_count=superseded_count,
            summary=(
                f"Scenario {case.name} memory comparison {outcome.value}: "
                f"hits={memory_hit_count}, writeback={writeback_count}, "
                f"quality_rejections={quality_rejection_count}, quarantined={quarantined_count}, "
                f"expired={expired_count}, superseded={superseded_count}."
            ),
        )

    def compare_cases(self, cases: list[ScenarioEvaluationCase]) -> ScenarioMemoryComparisonReport:
        results = [self.compare_case(case) for case in cases]
        improved_cases = sum(1 for result in results if result.improved)
        regressed_cases = sum(1 for result in results if result.regressed)
        unchanged_cases = sum(1 for result in results if result.unchanged)
        return ScenarioMemoryComparisonReport(
            total_cases=len(results),
            improved_cases=improved_cases,
            regressed_cases=regressed_cases,
            unchanged_cases=unchanged_cases,
            results=results,
            summary=(
                f"Scenario memory comparison completed: improved={improved_cases}, "
                f"regressed={regressed_cases}, unchanged={unchanged_cases}."
            ),
        )

    @staticmethod
    def _comparison_outcome(
        *,
        memory_off_result: ScenarioEvaluationResult,
        memory_on_result: ScenarioEvaluationResult,
    ) -> ScenarioMemoryComparisonOutcome:
        if memory_on_result.matched and not memory_off_result.matched:
            return ScenarioMemoryComparisonOutcome.IMPROVED
        if memory_off_result.matched and not memory_on_result.matched:
            return ScenarioMemoryComparisonOutcome.REGRESSED
        return ScenarioMemoryComparisonOutcome.UNCHANGED


__all__ = ["ScenarioEvaluationService", "ScenarioMemoryEvaluationService"]
