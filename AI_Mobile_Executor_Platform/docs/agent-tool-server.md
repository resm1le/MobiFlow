# Agent Tool Server

This document describes the Agent-facing tool protocol after the MCP compatibility
switch.

## Contract Boundary

`POST /mcp` is the standard Agent entry point. It exposes a Streamable
HTTP-compatible JSON-RPC facade with MCP-style `tools/list`, `tools/call`, and
`resources/read` semantics.

`/tools/**` is still retained during the migration, but it is no longer the
formal Agent protocol. It is the internal compatibility layer and rollback path
used by the MCP facade.

The Agent can select the adapter with:

- `PLATFORM_ADAPTER_KIND=mcp|http`
- `PLATFORM_MCP_URL=http://<control-service>/mcp`
- `PLATFORM_TOOL_BASE_URL=http://<control-service>/tools` for HTTP rollback

The default Agent adapter is `mcp`.

## MCP Methods

The facade currently supports:

- `initialize`
- `tools/list`
- `tools/call`
- `resources/read`

`tools/list` maps the existing `ToolFacadeService.catalog()` result to MCP tool
metadata:

- `name`
- `title`
- `description`
- `inputSchema`
- `annotations`
- `_meta`

MobiFlow-specific governance data remains in `_meta`:

- `mobiflow/toolKind`
- `mobiflow/riskLevel`
- `mobiflow/governance`
- `mobiflow/semanticTags`

MCP annotations are only client hints. Risk control, approval, idempotency, and
audit enforcement remain server-side responsibilities of `control-service`.

## Tool Calls

`tools/call` delegates normal tool execution to `ToolFacadeService.execute()`.
The MCP call arguments are converted into the existing `ExecuteToolRequest`:

- MCP `name` -> `ExecuteToolRequest.tool`
- MCP `arguments` -> `ExecuteToolRequest.arguments`
- MCP `sessionId` -> `ExecuteToolRequest.sessionId`
- MCP `callerContext` -> `ExecuteToolRequest.callerContext`

The response keeps the existing governed tool envelope in
`structuredContent`. A JSON text copy is also returned in MCP `content`.

The facade also exposes these compatibility tools:

- `resolve_confirmation`
- `query_audits`

## Approval Flow

Approval continues to use the existing governance model.

1. The Agent calls a governed tool through MCP `tools/call`.
2. The platform may return `status = approval_required`.
3. The Agent calls MCP tool `resolve_confirmation` with:
   - `confirmationId`
   - `decision = approve|reject`
   - `sessionId`
   - `callerContext`
4. The platform delegates to `ToolFacadeService.resolveConfirmation()`.

MCP elicitation is intentionally not introduced in this migration phase.

## Resources

Resource handles are exposed as MCP resource URIs:

```text
mobiflow://resource/{handle}
```

`resources/read` delegates to the existing resource read service and returns
text or JSON resources in MCP `contents`.

Binary resource download remains available through the existing handle download
path until the MCP resource path supports the full binary contract.

## Rollback

If the MCP facade or Agent adapter has to be bypassed, configure:

```text
PLATFORM_ADAPTER_KIND=http
PLATFORM_TOOL_BASE_URL=http://<control-service>/tools
```

This keeps all existing `/tools/**` behavior available during the migration.
