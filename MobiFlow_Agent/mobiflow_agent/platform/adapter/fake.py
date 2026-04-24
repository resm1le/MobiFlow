from __future__ import annotations

from typing import Any

from mobiflow_agent.common.contracts import EntityKind, ExecutionProposal, ObservationView
from mobiflow_agent.platform.adapter.protocol import PlatformAdapter, PlatformAdapterError
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


class FakePlatformAdapter(PlatformAdapter):
    def __init__(
        self,
        *,
        tool_catalog: list[ToolCatalogItem] | None = None,
        run_observations: dict[str, ObservationView | list[ObservationView]] | None = None,
        attempt_observations: dict[str, ObservationView | list[ObservationView]] | None = None,
        run_targets: dict[str, RunTargetContext] | None = None,
        attempts: dict[str, AttemptContext] | None = None,
        run_governance_snapshots: dict[str, RunGovernanceSnapshot] | None = None,
        run_lineage_snapshots: dict[str, RunLineageSnapshot] | None = None,
        generated_failure_triage: list[FailureTriageRecord] | None = None,
        latest_failure_triage: dict[str, FailureTriageRecord] | None = None,
        failure_triage_by_id: dict[str, FailureTriageRecord] | None = None,
        recovery_guidance: dict[str, RecoveryGuidance] | None = None,
        submit_results: list[GovernedActionResult] | None = None,
        resolve_results: list[GovernedActionResult] | None = None,
        resources: dict[str, dict[str, Any] | str | bytes] | None = None,
        audit_entries: list[AuditTimelineEntry] | None = None,
    ):
        self.tool_catalog = tool_catalog or []
        self.run_observations = run_observations or {}
        self.attempt_observations = attempt_observations or {}
        self.run_targets = run_targets or {}
        self.attempts = attempts or {}
        self.run_governance_snapshots = run_governance_snapshots or {}
        self.run_lineage_snapshots = run_lineage_snapshots or {}
        self.generated_failure_triage = generated_failure_triage or []
        self.latest_failure_triage = latest_failure_triage or {}
        self.failure_triage_by_id = failure_triage_by_id or {}
        self.recovery_guidance = recovery_guidance or {}
        self.submit_results = submit_results or []
        self.resolve_results = resolve_results or []
        self.resources = resources or {}
        self.audit_entries = audit_entries or []
        self.submitted_proposals: list[ExecutionProposal] = []

    def get_tool_catalog(self) -> list[ToolCatalogItem]:
        return list(self.tool_catalog)

    def observe_run(self, run_id: str) -> ObservationView:
        return self._next_observation(self.run_observations, run_id)

    def observe_attempt(self, attempt_id: str) -> ObservationView:
        return self._next_observation(self.attempt_observations, attempt_id)

    def observe_target(self, target_kind: EntityKind, target_id: str) -> ObservationView:
        if target_kind == EntityKind.RUN:
            return self.observe_run(target_id)
        if target_kind == EntityKind.ATTEMPT:
            return self.observe_attempt(target_id)
        raise PlatformAdapterError(
            "UNSUPPORTED_OBSERVATION_TARGET",
            f"FakePlatformAdapter cannot observe target kind {target_kind.value}.",
            retryable=False,
        )

    def get_run_target(self, run_target_id: str) -> RunTargetContext:
        return self.run_targets[run_target_id]

    def get_attempt(self, attempt_id: str) -> AttemptContext:
        return self.attempts[attempt_id]

    def get_run_governance_snapshot(self, run_id: str) -> RunGovernanceSnapshot:
        return self._next_value(self.run_governance_snapshots, run_id)

    def get_run_lineage_snapshot(self, run_id: str) -> RunLineageSnapshot:
        return self._next_value(self.run_lineage_snapshots, run_id)

    def generate_failure_triage(self, run_target_id: str) -> FailureTriageRecord:
        if not self.generated_failure_triage:
            raise PlatformAdapterError(
                "MISSING_GENERATE_FAILURE_TRIAGE_RESULT",
                "FakePlatformAdapter has no generated failure triage configured.",
            )
        return self.generated_failure_triage.pop(0)

    def get_latest_failure_triage(self, run_target_id: str) -> FailureTriageRecord:
        return self.latest_failure_triage[run_target_id]

    def get_failure_triage(self, triage_result_id: str) -> FailureTriageRecord:
        return self.failure_triage_by_id[triage_result_id]

    def get_recovery_guidance_context(self, run_id: str) -> RecoveryGuidance:
        return self.recovery_guidance[run_id]

    def submit_execution_proposal(
        self,
        proposal: ExecutionProposal,
        caller_context: CallerContext,
    ) -> GovernedActionResult:
        self.submitted_proposals.append(proposal)
        if not self.submit_results:
            raise PlatformAdapterError("MISSING_SUBMIT_RESULT", "FakePlatformAdapter has no submit result configured.")
        return self.submit_results.pop(0)

    def resolve_approval(
        self,
        confirmation_id: str,
        approved: bool,
        caller_context: CallerContext,
    ) -> GovernedActionResult:
        if not self.resolve_results:
            raise PlatformAdapterError("MISSING_RESOLVE_RESULT", "FakePlatformAdapter has no resolve result configured.")
        return self.resolve_results.pop(0)

    def read_resource(self, handle: str) -> dict[str, Any] | str | bytes:
        return self.resources[handle]

    def query_audit_timeline(self, **filters: str) -> list[AuditTimelineEntry]:
        return list(self.audit_entries)

    @staticmethod
    def _next_observation(
        source: dict[str, ObservationView | list[ObservationView]],
        key: str,
    ) -> ObservationView:
        return FakePlatformAdapter._next_value(source, key)

    @staticmethod
    def _next_value(
        source: dict[str, Any],
        key: str,
    ):
        value = source[key]
        if isinstance(value, list):
            if len(value) == 1:
                return value[0]
            return value.pop(0)
        return value


__all__ = ["FakePlatformAdapter"]
