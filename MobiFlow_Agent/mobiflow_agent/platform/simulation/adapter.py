from __future__ import annotations

from typing import Any

from mobiflow_agent.common.contracts import (
    EntityKind,
    EvidenceKind,
    EvidenceRef,
    ExecutionProposal,
    ObservationFact,
    ObservationFactSource,
    ObservationInference,
    ObservationView,
)
from mobiflow_agent.platform.adapter.protocol import PlatformAdapter, PlatformAdapterError
from mobiflow_agent.platform.simulation.models import (
    SimulatedActionTrace,
    SimulatedMobileScenario,
    SimulatedScreen,
    SimulatedTransition,
)
from mobiflow_agent.platform.types import (
    AuditTimelineEntry,
    AttemptContext,
    FailureTriageRecord,
    GovernedActionResult,
    GovernedActionState,
    PlatformEntityRefs,
    RecoveryGuidance,
    RunGovernanceSnapshot,
    RunLineageSnapshot,
    RunTargetContext,
    ToolAuditRef,
    ToolCatalogItem,
    ToolExecutionError,
    ToolRiskLevel,
)
from mobiflow_agent.runtime.state import CallerContext

SIMULATED_SCREEN_FACT_ID = "simulated_screen_snapshot"
SIMULATED_UI_TREE_FACT_ID = "simulated_ui_tree"
SIMULATED_ACTION_TRACE_FACT_ID = "simulated_latest_action_trace"

SUPPORTED_SIMULATED_ACTIONS = {
    "mobile.launch",
    "mobile.tap",
    "mobile.input_text",
    "mobile.back",
    "mobile.wait",
}


class SimulatedMobilePlatformAdapter(PlatformAdapter):
    def __init__(
        self,
        scenario: SimulatedMobileScenario,
        *,
        target_kind: EntityKind = EntityKind.TASK,
        target_id: str | None = None,
    ) -> None:
        self._scenario = scenario
        self._target_kind = target_kind
        self._target_id = target_id or scenario.scenario_id
        self._current_screen_id = scenario.initial_screen_id
        self._action_traces: list[SimulatedActionTrace] = []
        self._audit_entries: list[AuditTimelineEntry] = []
        self._pending_transitions: dict[str, tuple[ExecutionProposal, SimulatedTransition, CallerContext]] = {}

    @property
    def current_screen_id(self) -> str:
        return self._current_screen_id

    @property
    def action_traces(self) -> list[SimulatedActionTrace]:
        return list(self._action_traces)

    def get_tool_catalog(self) -> list[ToolCatalogItem]:
        return [
            ToolCatalogItem(
                name=action_name,
                title=action_name.replace(".", " ").title(),
                description=f"Simulated mobile action {action_name}.",
                tool_kind="simulated_action",
                risk_level=ToolRiskLevel.EXECUTION,
                requires_approval=False,
                input_schema={"type": "object"},
                semantic_tags=["mobile", "simulation"],
            )
            for action_name in sorted(SUPPORTED_SIMULATED_ACTIONS)
        ]

    def observe_target(self, target_kind: EntityKind, target_id: str) -> ObservationView:
        screen = self._screen()
        snapshot_ref = EvidenceRef(
            evidence_id=f"simulated:snapshot:{self._scenario.scenario_id}:{screen.screen_id}:{len(self._action_traces)}",
            kind=EvidenceKind.PLATFORM_SNAPSHOT,
            summary=f"Simulated screen {screen.screen_id}: {screen.title}.",
            locator=f"{self._scenario.scenario_id}:{screen.screen_id}",
            handle=f"sim://screen/{self._scenario.scenario_id}/{screen.screen_id}",
        )
        tree_ref = EvidenceRef(
            evidence_id=f"simulated:ui-tree:{self._scenario.scenario_id}:{screen.screen_id}:{len(self._action_traces)}",
            kind=EvidenceKind.ARTIFACT,
            summary=f"Simulated UI tree for {screen.title}.",
            locator=screen.screen_id,
            handle=f"sim://ui-tree/{self._scenario.scenario_id}/{screen.screen_id}",
        )
        screen_snapshot = screen.as_snapshot()
        screen_snapshot["metadata"] = {
            key: value for key, value in screen.metadata.items() if key != "auto_advance_to_after_observe"
        }
        facts = [
            ObservationFact(
                fact_id=SIMULATED_SCREEN_FACT_ID,
                source=ObservationFactSource.PLATFORM,
                title="Simulated screen snapshot",
                value=screen_snapshot,
                evidence_refs=[snapshot_ref],
            ),
            ObservationFact(
                fact_id=SIMULATED_UI_TREE_FACT_ID,
                source=ObservationFactSource.PLATFORM,
                title="Simulated UI tree",
                value=[node.as_tree() for node in screen.nodes],
                evidence_refs=[tree_ref],
            ),
        ]
        if self._action_traces:
            latest_trace = self._action_traces[-1]
            facts.append(
                ObservationFact(
                    fact_id=SIMULATED_ACTION_TRACE_FACT_ID,
                    source=ObservationFactSource.EXECUTOR,
                    title="Latest simulated action trace",
                    value=latest_trace.model_dump(mode="python"),
                    evidence_refs=[
                        EvidenceRef(
                            evidence_id=f"audit:{latest_trace.audit_id}",
                            kind=EvidenceKind.AUDIT,
                            summary=latest_trace.summary,
                            locator=latest_trace.audit_id,
                        )
                    ],
                )
            )
        inferences: list[ObservationInference] = []
        if screen.blocked_reason:
            inferences.append(
                ObservationInference(
                    inference_id=f"simulated:blocked:{screen.screen_id}",
                    statement=f"Simulated screen is blocked: {screen.blocked_reason}.",
                    based_on_fact_ids=[SIMULATED_SCREEN_FACT_ID],
                    confidence=0.99,
                )
            )
        observation = ObservationView(
            observation_id=f"observation:simulated:{self._scenario.scenario_id}:{screen.screen_id}:{len(self._action_traces)}",
            focus_kind=target_kind,
            focus_id=target_id,
            facts=facts,
            inferences=inferences,
            resource_handles=[snapshot_ref.handle or "", tree_ref.handle or ""],
        )
        auto_advance_to = screen.metadata.get("auto_advance_to_after_observe")
        if isinstance(auto_advance_to, str) and auto_advance_to in self._scenario.screens:
            self._current_screen_id = auto_advance_to
        return observation

    def observe_run(self, run_id: str) -> ObservationView:
        return self.observe_target(EntityKind.RUN, run_id)

    def observe_attempt(self, attempt_id: str) -> ObservationView:
        return self.observe_target(EntityKind.ATTEMPT, attempt_id)

    def submit_execution_proposal(
        self,
        proposal: ExecutionProposal,
        caller_context: CallerContext,
    ) -> GovernedActionResult:
        if proposal.action_tool_name not in SUPPORTED_SIMULATED_ACTIONS:
            return self._failed_result(
                proposal=proposal,
                caller_context=caller_context,
                code="UNSUPPORTED_SIMULATED_ACTION",
                message=f"Unsupported simulated mobile action: {proposal.action_tool_name}.",
            )
        transition = self._find_transition(proposal)
        if transition is None:
            return self._failed_result(
                proposal=proposal,
                caller_context=caller_context,
                code="SIMULATED_TRANSITION_NOT_FOUND",
                message=(
                    f"No simulated transition matched {proposal.action_tool_name} "
                    f"from screen {self._current_screen_id}."
                ),
            )
        if transition.requires_approval:
            confirmation_id = f"sim-confirm:{proposal.proposal_id}"
            self._pending_transitions[confirmation_id] = (proposal, transition, caller_context)
            trace = self._record_trace(
                proposal=proposal,
                caller_context=caller_context,
                state=GovernedActionState.APPROVAL_REQUIRED,
                to_screen_id=None,
                requires_approval=True,
                approved=None,
                summary=transition.confirmation_summary
                or f"Approval required for simulated action {proposal.action_tool_name}.",
            )
            return self._result(
                proposal=proposal,
                state=GovernedActionState.APPROVAL_REQUIRED,
                trace=trace,
                confirmation_id=confirmation_id,
                confirmation_summary=transition.confirmation_summary
                or f"Approve simulated action {proposal.action_tool_name}.",
            )
        return self._apply_transition(proposal=proposal, transition=transition, caller_context=caller_context)

    def resolve_approval(
        self,
        confirmation_id: str,
        approved: bool,
        caller_context: CallerContext,
    ) -> GovernedActionResult:
        pending = self._pending_transitions.pop(confirmation_id, None)
        if pending is None:
            proposal = ExecutionProposal(
                proposal_id=f"proposal:{confirmation_id}",
                action_tool_name="mobile.wait",
                arguments={"confirmation_id": confirmation_id},
                target_kind=self._target_kind,
                target_id=self._target_id,
                rationale="Resolve missing simulated approval.",
            )
            return self._failed_result(
                proposal=proposal,
                caller_context=caller_context,
                code="SIMULATED_CONFIRMATION_NOT_FOUND",
                message=f"No simulated approval is pending for confirmation {confirmation_id}.",
            )
        proposal, transition, original_context = pending
        if not approved:
            return self._failed_result(
                proposal=proposal,
                caller_context=caller_context,
                code="SIMULATED_APPROVAL_REJECTED",
                message=f"Simulated approval {confirmation_id} was rejected.",
            )
        return self._apply_transition(proposal=proposal, transition=transition, caller_context=original_context, approved=True)

    def read_resource(self, handle: str) -> dict[str, Any] | str | bytes:
        if handle in self._scenario.resources:
            return self._scenario.resources[handle]
        if handle.startswith("sim://screen/"):
            return self._screen().as_snapshot()
        if handle.startswith("sim://ui-tree/"):
            return [node.as_tree() for node in self._screen().nodes]
        if handle == f"sim://trace/{self._scenario.scenario_id}":
            return [trace.model_dump(mode="python") for trace in self._action_traces]
        raise PlatformAdapterError("SIMULATED_RESOURCE_NOT_FOUND", f"Unknown simulated resource: {handle}.")

    def query_audit_timeline(self, **filters: str) -> list[AuditTimelineEntry]:
        filtered = list(self._audit_entries)
        proposal_id = filters.get("proposal_id") or filters.get("proposalId")
        if proposal_id:
            filtered = [
                entry
                for entry in filtered
                if entry.entity_refs.proposal_id == proposal_id
            ]
        return filtered

    def get_run_target(self, run_target_id: str) -> RunTargetContext:
        raise PlatformAdapterError("UNSUPPORTED_SIMULATED_CONTEXT", "Simulation does not expose run target context.")

    def get_attempt(self, attempt_id: str) -> AttemptContext:
        raise PlatformAdapterError("UNSUPPORTED_SIMULATED_CONTEXT", "Simulation does not expose attempt context.")

    def get_run_governance_snapshot(self, run_id: str) -> RunGovernanceSnapshot:
        raise PlatformAdapterError("UNSUPPORTED_SIMULATED_CONTEXT", "Simulation does not expose run governance.")

    def get_run_lineage_snapshot(self, run_id: str) -> RunLineageSnapshot:
        raise PlatformAdapterError("UNSUPPORTED_SIMULATED_CONTEXT", "Simulation does not expose run lineage.")

    def generate_failure_triage(self, run_target_id: str) -> FailureTriageRecord:
        raise PlatformAdapterError("UNSUPPORTED_SIMULATED_CONTEXT", "Simulation does not generate failure triage.")

    def get_latest_failure_triage(self, run_target_id: str) -> FailureTriageRecord:
        raise PlatformAdapterError("UNSUPPORTED_SIMULATED_CONTEXT", "Simulation does not expose failure triage.")

    def get_failure_triage(self, triage_result_id: str) -> FailureTriageRecord:
        raise PlatformAdapterError("UNSUPPORTED_SIMULATED_CONTEXT", "Simulation does not expose failure triage.")

    def get_recovery_guidance_context(self, run_id: str) -> RecoveryGuidance:
        raise PlatformAdapterError("UNSUPPORTED_SIMULATED_CONTEXT", "Simulation does not expose recovery guidance.")

    def _apply_transition(
        self,
        *,
        proposal: ExecutionProposal,
        transition: SimulatedTransition,
        caller_context: CallerContext,
        approved: bool | None = None,
    ) -> GovernedActionResult:
        trace = self._record_trace(
            proposal=proposal,
            caller_context=caller_context,
            state=GovernedActionState.EXECUTED,
            to_screen_id=transition.to_screen_id,
            requires_approval=transition.requires_approval,
            approved=approved,
            summary=transition.summary
            or f"Simulated action {proposal.action_tool_name} moved to {transition.to_screen_id}.",
        )
        self._current_screen_id = transition.to_screen_id
        return self._result(
            proposal=proposal,
            state=GovernedActionState.EXECUTED,
            trace=trace,
            result={
                "fromScreenId": trace.from_screen_id,
                "toScreenId": trace.to_screen_id,
                "screen": self._screen().as_snapshot(),
                **transition.result,
            },
        )

    def _failed_result(
        self,
        *,
        proposal: ExecutionProposal,
        caller_context: CallerContext,
        code: str,
        message: str,
    ) -> GovernedActionResult:
        trace = self._record_trace(
            proposal=proposal,
            caller_context=caller_context,
            state=GovernedActionState.FAILED,
            to_screen_id=None,
            requires_approval=False,
            approved=None,
            error_code=code,
            summary=message,
        )
        return self._result(
            proposal=proposal,
            state=GovernedActionState.FAILED,
            trace=trace,
            error=ToolExecutionError(code=code, message=message, retryable=False),
        )

    def _find_transition(self, proposal: ExecutionProposal) -> SimulatedTransition | None:
        for transition in self._scenario.transitions:
            if transition.matches(
                action_tool_name=proposal.action_tool_name,
                from_screen_id=self._current_screen_id,
                arguments=proposal.arguments,
            ):
                return transition
        return None

    def _screen(self) -> SimulatedScreen:
        return self._scenario.screens[self._current_screen_id]

    def _record_trace(
        self,
        *,
        proposal: ExecutionProposal,
        caller_context: CallerContext,
        state: GovernedActionState,
        to_screen_id: str | None,
        requires_approval: bool,
        approved: bool | None,
        summary: str,
        error_code: str | None = None,
    ) -> SimulatedActionTrace:
        sequence = len(self._action_traces) + 1
        audit_id = f"sim-audit:{self._scenario.scenario_id}:{sequence}"
        trace = SimulatedActionTrace(
            sequence=sequence,
            proposal_id=proposal.proposal_id,
            action_tool_name=proposal.action_tool_name,
            from_screen_id=self._current_screen_id,
            to_screen_id=to_screen_id,
            state=state,
            audit_id=audit_id,
            arguments=proposal.arguments,
            requires_approval=requires_approval,
            approved=approved,
            error_code=error_code,
            summary=summary,
        )
        self._action_traces.append(trace)
        self._audit_entries.append(
            AuditTimelineEntry(
                audit=ToolAuditRef(audit_id=audit_id, risk_level=ToolRiskLevel.EXECUTION),
                request_id=proposal.proposal_id,
                session_id=caller_context.session_id,
                tool=proposal.action_tool_name,
                status=state.value,
                caller_context=caller_context.model_dump(mode="python"),
                entity_refs=self._entity_refs(proposal),
                created_at=sequence,
                updated_at=sequence,
            )
        )
        return trace

    def _result(
        self,
        *,
        proposal: ExecutionProposal,
        state: GovernedActionState,
        trace: SimulatedActionTrace,
        result: dict[str, Any] | None = None,
        confirmation_id: str | None = None,
        confirmation_summary: str | None = None,
        error: ToolExecutionError | None = None,
    ) -> GovernedActionResult:
        return GovernedActionResult(
            state=state,
            proposal_id=proposal.proposal_id,
            action_tool_name=proposal.action_tool_name,
            audit=ToolAuditRef(audit_id=trace.audit_id, risk_level=ToolRiskLevel.EXECUTION),
            entity_refs=self._entity_refs(proposal),
            confirmation_id=confirmation_id,
            confirmation_summary=confirmation_summary,
            result=result or {
                "trace": trace.model_dump(mode="python"),
                "currentScreenId": self._current_screen_id,
            },
            error=error,
        )

    def _entity_refs(self, proposal: ExecutionProposal) -> PlatformEntityRefs:
        return PlatformEntityRefs(
            proposal_id=proposal.proposal_id,
            run_id=proposal.target_id if proposal.target_kind == EntityKind.RUN else None,
            task_id=proposal.target_id if proposal.target_kind == EntityKind.TASK else None,
        )


__all__ = [
    "SIMULATED_ACTION_TRACE_FACT_ID",
    "SIMULATED_SCREEN_FACT_ID",
    "SIMULATED_UI_TREE_FACT_ID",
    "SUPPORTED_SIMULATED_ACTIONS",
    "SimulatedMobilePlatformAdapter",
]
