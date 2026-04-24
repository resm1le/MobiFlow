from __future__ import annotations

from typing import Any, Protocol

from mobiflow_agent.common.contracts import EntityKind, ExecutionProposal, ObservationView
from mobiflow_agent.platform.types import (
    AuditTimelineEntry,
    AttemptContext,
    FailureTriageRecord,
    GovernedActionResult,
    RecoveryGuidance,
    RunGovernanceSnapshot,
    RunLineageSnapshot,
    RunTargetContext,
    ToolCatalogItem,
)
from mobiflow_agent.runtime.state import CallerContext


class PlatformAdapterError(RuntimeError):
    def __init__(self, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class PlatformAdapter(Protocol):
    def get_tool_catalog(self) -> list[ToolCatalogItem]:
        """Return platform tool semantics needed by the runtime."""

    def observe_run(self, run_id: str) -> ObservationView:
        """Return a run-centric observation view."""

    def observe_attempt(self, attempt_id: str) -> ObservationView:
        """Return an attempt-centric observation view."""

    def observe_target(self, target_kind: EntityKind, target_id: str) -> ObservationView:
        """Return an observation view for a typed task target."""

    def get_run_target(self, run_target_id: str) -> RunTargetContext:
        """Return minimal run-target context needed by advisory flows."""

    def get_attempt(self, attempt_id: str) -> AttemptContext:
        """Return minimal attempt context needed by advisory flows."""

    def get_run_governance_snapshot(self, run_id: str) -> RunGovernanceSnapshot:
        """Return the typed run governance snapshot."""

    def get_run_lineage_snapshot(self, run_id: str) -> RunLineageSnapshot:
        """Return the typed run lineage snapshot."""

    def generate_failure_triage(self, run_target_id: str) -> FailureTriageRecord:
        """Generate a canonical failure-triage result."""

    def get_latest_failure_triage(self, run_target_id: str) -> FailureTriageRecord:
        """Read the latest canonical failure-triage result."""

    def get_failure_triage(self, triage_result_id: str) -> FailureTriageRecord:
        """Read a canonical failure-triage result by id."""

    def get_recovery_guidance_context(self, run_id: str) -> RecoveryGuidance:
        """Return advisory recovery guidance for a run."""

    def submit_execution_proposal(
        self,
        proposal: ExecutionProposal,
        caller_context: CallerContext,
    ) -> GovernedActionResult:
        """Submit the proposal through platform-governed execution."""

    def resolve_approval(
        self,
        confirmation_id: str,
        approved: bool,
        caller_context: CallerContext,
    ) -> GovernedActionResult:
        """Resolve a pending approval and return the execution outcome."""

    def read_resource(self, handle: str) -> dict[str, Any] | str | bytes:
        """Read a resource handle returned by the platform."""

    def query_audit_timeline(self, **filters: str) -> list[AuditTimelineEntry]:
        """Query audit entries scoped by platform lineage fields."""


__all__ = ["PlatformAdapter", "PlatformAdapterError"]
