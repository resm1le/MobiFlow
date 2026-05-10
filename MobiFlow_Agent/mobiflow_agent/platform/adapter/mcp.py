from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from typing import Any, Protocol
from urllib import error, parse, request

from mobiflow_agent.common.contracts import EntityKind, ExecutionProposal, ObservationView
from mobiflow_agent.platform.adapter.mapping import (
    caller_context_payload,
    map_audit_entry,
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
    ToolRiskLevel,
)
from mobiflow_agent.runtime.state import CallerContext


class McpJsonRpcTransport(Protocol):
    def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Call an MCP JSON-RPC method and return the method result."""


@dataclass(slots=True)
class UrlLibMcpJsonRpcTransport:
    endpoint_url: str
    bearer_token: str | None = None
    timeout_seconds: float = 15.0
    _request_index: int = 0

    def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._request_index += 1
        payload = {
            "jsonrpc": "2.0",
            "id": f"mcp-request:{self._request_index}",
            "method": method,
            "params": params or {},
        }
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        req = request.Request(
            self.endpoint_url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                content = response.read().decode("utf-8")
        except error.HTTPError as exc:
            content = exc.read().decode("utf-8", errors="replace")
            raise PlatformAdapterError("MCP_HTTP_ERROR", content or f"http_{exc.code}", retryable=exc.code >= 500) from exc
        except OSError as exc:
            raise PlatformAdapterError("MCP_TRANSPORT_ERROR", str(exc), retryable=True) from exc
        envelope = json.loads(content) if content else {}
        if envelope.get("error") is not None:
            error_payload = envelope["error"]
            raise PlatformAdapterError(
                str(error_payload.get("code", "MCP_ERROR")),
                error_payload.get("message", "MCP call failed."),
                retryable=False,
            )
        result = envelope.get("result")
        return result if isinstance(result, dict) else {}


class McpPlatformAdapter(PlatformAdapter):
    def __init__(
        self,
        endpoint_url: str | None = None,
        bearer_token: str | None = None,
        transport: McpJsonRpcTransport | None = None,
    ):
        resolved_endpoint_url = endpoint_url or os.environ.get("PLATFORM_MCP_URL", "").strip()
        if not resolved_endpoint_url and transport is None:
            raise ValueError("McpPlatformAdapter requires PLATFORM_MCP_URL or an explicit transport.")
        self._transport = transport or UrlLibMcpJsonRpcTransport(
            endpoint_url=resolved_endpoint_url,
            bearer_token=bearer_token or os.environ.get("PLATFORM_TOOL_BEARER_TOKEN"),
        )

    def get_tool_catalog(self) -> list[ToolCatalogItem]:
        result = self._transport.call("tools/list")
        return [self._map_mcp_tool(tool) for tool in result.get("tools", [])]

    def observe_run(self, run_id: str) -> ObservationView:
        governance = self._call_tool("get_run_governance_snapshot", {"runId": run_id})
        lineage = self._call_tool("get_run_lineage_snapshot", {"runId": run_id})
        latest_attempt_ids = (
            governance.get("result", {}).get("latestAttemptIds", [])
            or lineage.get("result", {}).get("latestAttemptIds", [])
            or []
        )
        diagnosis = None
        if latest_attempt_ids:
            diagnosis = self._call_tool("get_attempt_diagnosis_bundle", {"attemptId": latest_attempt_ids[0]})
        return build_run_observation_view(
            run_id=run_id,
            governance_response=governance,
            lineage_response=lineage,
            diagnosis_response=diagnosis,
        )

    def observe_attempt(self, attempt_id: str) -> ObservationView:
        diagnosis = self._call_tool("get_attempt_diagnosis_bundle", {"attemptId": attempt_id})
        return build_attempt_observation_view(attempt_id=attempt_id, diagnosis_response=diagnosis)

    def observe_target(self, target_kind: EntityKind, target_id: str) -> ObservationView:
        if target_kind == EntityKind.RUN:
            return self.observe_run(target_id)
        if target_kind == EntityKind.ATTEMPT:
            return self.observe_attempt(target_id)
        raise PlatformAdapterError(
            "UNSUPPORTED_OBSERVATION_TARGET",
            f"McpPlatformAdapter cannot observe target kind {target_kind.value}.",
            retryable=False,
        )

    def get_run_target(self, run_target_id: str) -> RunTargetContext:
        response = self._call_tool("get_run_target", {"runTargetId": run_target_id})
        return map_run_target_context(require_completed_tool_result("get_run_target", response))

    def get_attempt(self, attempt_id: str) -> AttemptContext:
        response = self._call_tool("get_attempt", {"attemptId": attempt_id})
        return map_attempt_context(require_completed_tool_result("get_attempt", response).get("attempt") or {})

    def get_run_governance_snapshot(self, run_id: str) -> RunGovernanceSnapshot:
        response = self._call_tool("get_run_governance_snapshot", {"runId": run_id})
        return map_run_governance_snapshot(require_completed_tool_result("get_run_governance_snapshot", response))

    def get_run_lineage_snapshot(self, run_id: str) -> RunLineageSnapshot:
        response = self._call_tool("get_run_lineage_snapshot", {"runId": run_id})
        return map_run_lineage_snapshot(require_completed_tool_result("get_run_lineage_snapshot", response))

    def generate_failure_triage(self, run_target_id: str) -> FailureTriageRecord:
        response = self._call_tool("generate_failure_triage", {"runTargetId": run_target_id})
        return map_failure_triage_record(require_completed_tool_result("generate_failure_triage", response))

    def get_latest_failure_triage(self, run_target_id: str) -> FailureTriageRecord:
        response = self._call_tool("get_latest_failure_triage", {"runTargetId": run_target_id})
        return map_failure_triage_record(require_completed_tool_result("get_latest_failure_triage", response))

    def get_failure_triage(self, triage_result_id: str) -> FailureTriageRecord:
        response = self._call_tool("get_failure_triage", {"triageResultId": triage_result_id})
        return map_failure_triage_record(require_completed_tool_result("get_failure_triage", response))

    def get_recovery_guidance_context(self, run_id: str) -> RecoveryGuidance:
        response = self._call_tool("get_recovery_guidance_context", {"runId": run_id})
        return map_recovery_guidance(require_completed_tool_result("get_recovery_guidance_context", response))

    def submit_execution_proposal(
        self,
        proposal: ExecutionProposal,
        caller_context: CallerContext,
    ) -> GovernedActionResult:
        response = self._call_tool(
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
        response = self._call_tool(
            "resolve_confirmation",
            {
                "confirmationId": confirmation_id,
                "decision": "approve" if approved else "reject",
            },
            caller_context=caller_context,
        )
        entity_refs = map_entity_refs(response.get("entityRefs"))
        proposal_id = entity_refs.proposal_id if entity_refs else f"confirmation:{confirmation_id}"
        action_tool_name = response.get("tool") or "resolve_confirmation"
        return map_governed_action_result(response, proposal_id, action_tool_name)

    def read_resource(self, handle: str) -> dict[str, Any] | str | bytes:
        uri = f"mobiflow://resource/{parse.quote(handle, safe='')}"
        result = self._transport.call("resources/read", {"uri": uri})
        contents = result.get("contents") or []
        if not contents:
            raise PlatformAdapterError("MCP_RESOURCE_EMPTY", "MCP resource read returned no content.", retryable=False)
        content = contents[0]
        mime_type = (content.get("mimeType") or "").lower()
        if "blob" in content:
            return base64.b64decode(content["blob"])
        text = content.get("text", "")
        if mime_type.startswith("application/json") or mime_type.endswith("+json") or mime_type.endswith("/json"):
            return json.loads(text) if text else {}
        return text

    def query_audit_timeline(self, **filters: str) -> list[AuditTimelineEntry]:
        response = self._call_tool("query_audits", {key: value for key, value in filters.items() if value})
        entries = response.get("entries", []) if response.get("version") else require_completed_tool_result("query_audits", response).get("entries", [])
        return [map_audit_entry(entry) for entry in entries]

    def _call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        caller_context: CallerContext | None = None,
    ) -> dict[str, Any]:
        params = {
            "name": name,
            "arguments": {key: value for key, value in arguments.items() if value is not None},
            "sessionId": caller_context.session_id if caller_context else "mobiflow-agent",
        }
        if caller_context is not None:
            params["requestId"] = (
                f"{name}:{arguments.get('runId') or arguments.get('attemptId') or arguments.get('proposalId') or 'request'}"
            )
            params["callerContext"] = caller_context_payload(caller_context)
        result = self._transport.call("tools/call", params)
        response = self._structured_content(result)
        status = response.get("status")
        if status not in {"completed", "approval_required", "failed"} and "entries" not in response:
            raise PlatformAdapterError("INVALID_MCP_TOOL_STATUS", f"Unsupported MCP tool status: {status}", retryable=False)
        return response

    @staticmethod
    def _structured_content(result: dict[str, Any]) -> dict[str, Any]:
        structured = result.get("structuredContent")
        if isinstance(structured, dict):
            return structured
        for item in result.get("content") or []:
            if isinstance(item, dict) and item.get("type") == "text":
                try:
                    loaded = json.loads(item.get("text") or "{}")
                except json.JSONDecodeError as exc:
                    raise PlatformAdapterError("INVALID_MCP_TOOL_CONTENT", "MCP tool content was not JSON.", retryable=False) from exc
                if isinstance(loaded, dict):
                    return loaded
        raise PlatformAdapterError("INVALID_MCP_TOOL_RESULT", "MCP tool result did not include structured content.", retryable=False)

    @staticmethod
    def _map_mcp_tool(tool: dict[str, Any]) -> ToolCatalogItem:
        meta = tool.get("_meta") or {}
        governance = meta.get("mobiflow/governance") or {}
        risk_level = str(meta.get("mobiflow/riskLevel") or ToolRiskLevel.DISCOVERY.value).lower()
        return ToolCatalogItem(
            name=tool["name"],
            title=tool.get("title"),
            description=tool.get("description"),
            tool_kind=str(meta.get("mobiflow/toolKind") or "tool"),
            risk_level=ToolRiskLevel(risk_level),
            requires_approval=bool(governance.get("requiresApproval", False)),
            confirmation_mode=governance.get("confirmationMode"),
            input_schema=dict(tool.get("inputSchema") or {}),
            semantic_tags=list(meta.get("mobiflow/semanticTags") or []),
        )


__all__ = ["McpJsonRpcTransport", "McpPlatformAdapter", "UrlLibMcpJsonRpcTransport"]
