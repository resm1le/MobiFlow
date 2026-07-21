from __future__ import annotations

from mobiflow_agent.collection.compiler import DispatchPlanCompiler
from mobiflow_agent.collection.models import (
    CollectionDispatchResult,
    CollectionDispatchStatus,
    CollectionIntent,
    DispatchPlan,
    IntentPlanningResult,
)
from mobiflow_agent.collection.planner import IntentPlanner
from mobiflow_agent.collection.protocol import CollectionDispatchPlatform
from mobiflow_agent.platform.adapter.protocol import PlatformAdapterError
from mobiflow_agent.platform.types import GovernedActionState
from mobiflow_agent.runtime.state import CallerContext
from mobiflow_agent.waypoint.catalog import SequenceCatalog


class CollectionDispatchService:
    def __init__(
        self,
        *,
        platform: CollectionDispatchPlatform,
        sequence_catalog: SequenceCatalog,
        intent_planner: IntentPlanner,
        compiler: DispatchPlanCompiler,
    ) -> None:
        self._platform = platform
        self._sequence_catalog = sequence_catalog
        self._intent_planner = intent_planner
        self._compiler = compiler

    def plan_intent(
        self,
        intent: CollectionIntent,
        caller_context: CallerContext,
    ) -> CollectionDispatchResult:
        try:
            devices = self._platform.list_devices()
            planning_catalog = self._platform.get_run_planning_catalog()
        except PlatformAdapterError as exc:
            return self._platform_error(exc)

        planning = self._intent_planner.plan(
            intent,
            sequence_catalog=self._sequence_catalog,
            devices=devices,
            planning_catalog=planning_catalog,
        )
        if planning.status != CollectionDispatchStatus.PLANNED or planning.plan is None:
            return CollectionDispatchResult(
                status=planning.status,
                issues=list(planning.issues),
                clarification_questions=list(planning.clarification_questions),
                trace_refs=_dedupe(planning.trace_refs),
            )
        return self._compile_discovered(
            intent,
            planning.plan,
            caller_context=caller_context,
            devices=devices,
            planning_catalog=planning_catalog,
            planning=planning,
        )

    def submit_intent(
        self,
        intent: CollectionIntent,
        caller_context: CallerContext,
    ) -> CollectionDispatchResult:
        return self._submit_prepared(self.plan_intent(intent, caller_context), caller_context)

    def submit_plan(
        self,
        intent: CollectionIntent,
        plan: DispatchPlan,
        caller_context: CallerContext,
    ) -> CollectionDispatchResult:
        try:
            devices = self._platform.list_devices()
            planning_catalog = self._platform.get_run_planning_catalog()
        except PlatformAdapterError as exc:
            return self._platform_error(exc, plan=plan)
        prepared = self._compile_discovered(
            intent,
            plan,
            caller_context=caller_context,
            devices=devices,
            planning_catalog=planning_catalog,
            planning=IntentPlanningResult(
                status=CollectionDispatchStatus.PLANNED,
                plan=plan,
                confidence=1.0,
            ),
        )
        return self._submit_prepared(prepared, caller_context)

    def _compile_discovered(
        self,
        intent: CollectionIntent,
        plan: DispatchPlan,
        *,
        caller_context: CallerContext,
        devices,
        planning_catalog,
        planning: IntentPlanningResult,
    ) -> CollectionDispatchResult:
        compiled = self._compiler.compile(
            intent,
            plan,
            sequence_catalog=self._sequence_catalog,
            devices=devices,
            planning_catalog=planning_catalog,
            caller_context=caller_context,
            planning_confidence=planning.confidence,
        )
        if not compiled.accepted or compiled.proposal is None:
            return CollectionDispatchResult(
                status=CollectionDispatchStatus.REJECTED,
                plan=plan,
                issues=_dedupe([*planning.issues, *compiled.issues]),
                warnings=_dedupe(compiled.warnings),
                trace_refs=_dedupe(planning.trace_refs),
            )
        return CollectionDispatchResult(
            status=CollectionDispatchStatus.PLANNED,
            plan=plan,
            proposal=compiled.proposal,
            issues=_dedupe(planning.issues),
            warnings=_dedupe(compiled.warnings),
            trace_refs=_dedupe(planning.trace_refs),
        )

    def _submit_prepared(
        self,
        prepared: CollectionDispatchResult,
        caller_context: CallerContext,
    ) -> CollectionDispatchResult:
        if prepared.status != CollectionDispatchStatus.PLANNED:
            return prepared
        assert prepared.plan is not None and prepared.proposal is not None
        try:
            governed = self._platform.submit_execution_proposal(
                prepared.proposal,
                caller_context,
            )
        except PlatformAdapterError as exc:
            return self._platform_error(
                exc,
                plan=prepared.plan,
                warnings=prepared.warnings,
                trace_refs=prepared.trace_refs,
            )
        status = {
            GovernedActionState.APPROVAL_REQUIRED: CollectionDispatchStatus.APPROVAL_REQUIRED,
            GovernedActionState.EXECUTED: CollectionDispatchStatus.EXECUTED,
            GovernedActionState.FAILED: CollectionDispatchStatus.FAILED,
        }[governed.state]
        return CollectionDispatchResult(
            status=status,
            plan=prepared.plan,
            proposal=prepared.proposal,
            governed_result=governed,
            issues=list(prepared.issues),
            warnings=_dedupe([*prepared.warnings, *governed.warnings]),
            trace_refs=_dedupe(prepared.trace_refs),
        )

    @staticmethod
    def _platform_error(
        exc: PlatformAdapterError,
        *,
        plan: DispatchPlan | None = None,
        warnings: list[str] | None = None,
        trace_refs: list[str] | None = None,
    ) -> CollectionDispatchResult:
        return CollectionDispatchResult(
            status=CollectionDispatchStatus.ERROR,
            plan=plan,
            issues=[
                f"platform_error:{exc.code}:retryable={str(exc.retryable).lower()}:{exc.message}"
            ],
            warnings=list(warnings or []),
            trace_refs=_dedupe(trace_refs or []),
        )


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


__all__ = ["CollectionDispatchService"]
