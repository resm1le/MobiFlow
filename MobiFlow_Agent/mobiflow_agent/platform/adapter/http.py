from __future__ import annotations

import json
import os
from typing import Any
from urllib import parse

from mobiflow_agent.common.contracts import EntityKind, ExecutionProposal, ObservationView
from mobiflow_agent.platform.adapter.mapping import (
    caller_context_payload,
    map_audit_entry,
    map_catalog_item,
    map_entity_refs,
    map_failure_triage_record,
    map_governed_action_result,
    map_recovery_guidance,
    map_run_governance_snapshot,
    map_run_lineage_snapshot,
    map_run_target_context,
    map_attempt_context,
    require_completed_tool_result,
)
from mobiflow_agent.platform.adapter.protocol import PlatformAdapter, PlatformAdapterError
from mobiflow_agent.platform.adapter.transport import PROTOCOL_VERSION, ToolRuntimeTransport, UrlLibToolRuntimeTransport
from mobiflow_agent.platform.evidence import build_attempt_observation_view, build_run_observation_view
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


class HttpPlatformAdapter(PlatformAdapter):
    def __init__(
        self,
        base_url: str | None = None,
        bearer_token: str | None = None,
        transport: ToolRuntimeTransport | None = None,
    ):
        resolved_base_url = base_url or os.environ.get("PLATFORM_TOOL_BASE_URL", "").strip()
        if not resolved_base_url and transport is None:
            raise ValueError("HttpPlatformAdapter requires PLATFORM_TOOL_BASE_URL or an explicit transport.")
        self._transport = transport or UrlLibToolRuntimeTransport(
            base_url=resolved_base_url,
            bearer_token=bearer_token or os.environ.get("PLATFORM_TOOL_BEARER_TOKEN"),
        )

    def get_tool_catalog(self) -> list[ToolCatalogItem]:
        response = self._transport.request_json("GET", "/tools/catalog")
        return [map_catalog_item(item) for item in response.get("tools", [])]

    def observe_run(self, run_id: str) -> ObservationView:
        governance = self._execute_tool("get_run_governance_snapshot", {"runId": run_id})
        lineage = self._execute_tool("get_run_lineage_snapshot", {"runId": run_id})
        latest_attempt_ids = (
            governance.get("result", {}).get("latestAttemptIds", [])
            or lineage.get("result", {}).get("latestAttemptIds", [])
            or []
        )
        diagnosis = None
        if latest_attempt_ids:
            diagnosis = self._execute_tool("get_attempt_diagnosis_bundle", {"attemptId": latest_attempt_ids[0]})
        return build_run_observation_view(
            run_id=run_id,
            governance_response=governance,
            lineage_response=lineage,
            diagnosis_response=diagnosis,
        )

    def observe_attempt(self, attempt_id: str) -> ObservationView:
        diagnosis = self._execute_tool("get_attempt_diagnosis_bundle", {"attemptId": attempt_id})
        return build_attempt_observation_view(attempt_id=attempt_id, diagnosis_response=diagnosis)

    def observe_target(self, target_kind: EntityKind, target_id: str) -> ObservationView:
        if target_kind == EntityKind.RUN:
            return self.observe_run(target_id)
        if target_kind == EntityKind.ATTEMPT:
            return self.observe_attempt(target_id)
        raise PlatformAdapterError(
            "UNSUPPORTED_OBSERVATION_TARGET",
            f"HttpPlatformAdapter cannot observe target kind {target_kind.value}.",
            retryable=False,
        )

    def get_run_target(self, run_target_id: str) -> RunTargetContext:
        response = self._execute_tool("get_run_target", {"runTargetId": run_target_id})
        return map_run_target_context(require_completed_tool_result("get_run_target", response))

    def get_attempt(self, attempt_id: str) -> AttemptContext:
        response = self._execute_tool("get_attempt", {"attemptId": attempt_id})
        return map_attempt_context(require_completed_tool_result("get_attempt", response).get("attempt") or {})

    def get_run_governance_snapshot(self, run_id: str) -> RunGovernanceSnapshot:
        response = self._execute_tool("get_run_governance_snapshot", {"runId": run_id})
        return map_run_governance_snapshot(require_completed_tool_result("get_run_governance_snapshot", response))

    def get_run_lineage_snapshot(self, run_id: str) -> RunLineageSnapshot:
        response = self._execute_tool("get_run_lineage_snapshot", {"runId": run_id})
        return map_run_lineage_snapshot(require_completed_tool_result("get_run_lineage_snapshot", response))

    def generate_failure_triage(self, run_target_id: str) -> FailureTriageRecord:
        response = self._execute_tool("generate_failure_triage", {"runTargetId": run_target_id})
        return map_failure_triage_record(require_completed_tool_result("generate_failure_triage", response))

    def get_latest_failure_triage(self, run_target_id: str) -> FailureTriageRecord:
        response = self._execute_tool("get_latest_failure_triage", {"runTargetId": run_target_id})
        return map_failure_triage_record(require_completed_tool_result("get_latest_failure_triage", response))

    def get_failure_triage(self, triage_result_id: str) -> FailureTriageRecord:
        response = self._execute_tool("get_failure_triage", {"triageResultId": triage_result_id})
        return map_failure_triage_record(require_completed_tool_result("get_failure_triage", response))

    def get_recovery_guidance_context(self, run_id: str) -> RecoveryGuidance:
        response = self._execute_tool("get_recovery_guidance_context", {"runId": run_id})
        return map_recovery_guidance(require_completed_tool_result("get_recovery_guidance_context", response))

    def submit_execution_proposal(
        self,
        proposal: ExecutionProposal,
        caller_context: CallerContext,
    ) -> GovernedActionResult:
        response = self._execute_tool(
            "propose_governed_action",
            {
                "proposalId": proposal.proposal_id,
                "actionToolName": proposal.action_tool_name,
                "arguments": proposal.arguments,
                "targetKind": proposal.target_kind.value if proposal.target_kind else None,
                "targetId": proposal.target_id,
                "rationale": proposal.rationale,
                "preconditions": proposal.preconditions,
                "confidence": proposal.confidence,
            },
            caller_context=caller_context,
        )
        return map_governed_action_result(response, proposal.proposal_id, proposal.action_tool_name)

    def resolve_approval(
        self,
        confirmation_id: str,
        approved: bool,
        caller_context: CallerContext,
    ) -> GovernedActionResult:
        response = self._transport.request_json(
            "POST",
            "/tools/confirmations/resolve",
            {
                "version": PROTOCOL_VERSION,
                "confirmationId": confirmation_id,
                "decision": "approve" if approved else "reject",
                "sessionId": caller_context.session_id,
                "callerContext": caller_context_payload(caller_context),
            },
        )
        entity_refs = map_entity_refs(response.get("entityRefs"))
        proposal_id = entity_refs.proposal_id if entity_refs else f"confirmation:{confirmation_id}"
        action_tool_name = response.get("tool") or "propose_governed_action"
        return map_governed_action_result(response, proposal_id, action_tool_name)

    def read_resource(self, handle: str) -> dict[str, Any] | str | bytes:
        response = self._transport.request_json("POST", "/tools/resources/read", {"handle": handle})
        mime_type = (response.get("mimeType") or "").lower()
        content = response.get("content")
        if mime_type.startswith("application/json") and isinstance(content, (dict, list)):
            return content
        if mime_type.startswith("text/") or mime_type.endswith("+json") or mime_type.endswith("/json"):
            return content if isinstance(content, str) else json.dumps(content, ensure_ascii=True)
        encoded_handle = parse.quote(handle, safe="")
        return self._transport.download_bytes(f"/tools/resources/{encoded_handle}/download")

    def query_audit_timeline(self, **filters: str) -> list[AuditTimelineEntry]:
        payload = {key: value for key, value in filters.items() if value}
        response = self._transport.request_json("POST", "/tools/audits/query", payload)
        return [map_audit_entry(entry) for entry in response.get("entries", [])]

    def _execute_tool(
        self,
        tool: str,
        arguments: dict[str, Any],
        caller_context: CallerContext | None = None,
    ) -> dict[str, Any]:
        response = self._transport.request_json(
            "POST",
            "/tools/execute",
            {
                "version": PROTOCOL_VERSION,
                "requestId": f"{tool}:{arguments.get('runId') or arguments.get('attemptId') or arguments.get('proposalId') or 'request'}",
                "sessionId": caller_context.session_id if caller_context else "mobiflow-agent",
                "tool": tool,
                "arguments": {key: value for key, value in arguments.items() if value is not None},
                "callerContext": caller_context_payload(caller_context) if caller_context else None,
            },
        )
        status = response.get("status")
        if status not in {"completed", "approval_required", "failed"}:
            raise PlatformAdapterError("INVALID_TOOL_STATUS", f"Unsupported tool status: {status}", retryable=False)
        return response


__all__ = ["HttpPlatformAdapter"]
