# Platform Protocol Overview

MobiFlow currently exposes four protocol surfaces:

- `/executor/**` for Android executor nodes
- `/api/**` for console and operator APIs
- `/mcp` for Agent tool access
- `/tools/**` as the internal compatibility implementation behind `/mcp`

## Executor Protocol

Android executors use the signed pull-based HTTP protocol under `/executor/**`.
The main endpoints are:

- `POST /executor/register`
- `POST /executor/heartbeat`
- `POST /executor/tasks/claim`
- `POST /executor/tasks/{attemptId}/start`
- `POST /executor/tasks/{attemptId}/events`
- `POST /executor/tasks/{attemptId}/finish`
- `POST /executor/tasks/{attemptId}/artifacts/uploads`
- `POST /executor/tasks/{attemptId}/artifacts/uploads/{artifactId}/finalize`

Executors claim work from the control plane, execute task attempts, stream
events, and upload artifacts through the artifact ticket flow.

## Admin And Operator API

`/api/**` is used by the console and operator workflows. It is not the Agent
tool contract.

Main domain objects include:

- devices
- device pools
- runs
- tasks
- attempts
- artifacts
- AI run plan
- AI run summary
- AI failure triage

## Agent MCP Protocol

`/mcp` is the standard Agent-facing protocol. It is a JSON-RPC endpoint exposing
MCP-style methods:

- `initialize`
- `tools/list`
- `tools/call`
- `resources/read`

The Agent selects this path with:

```text
PLATFORM_ADAPTER_KIND=mcp
PLATFORM_MCP_URL=http://<control-service>/mcp
```

This is the default adapter kind.

### Tool Catalog

`tools/list` maps the existing platform tool catalog into MCP metadata:

- `name`
- `title`
- `description`
- `inputSchema`
- `annotations`
- `_meta`

MobiFlow governance fields are preserved in `_meta`, including risk level,
approval policy, tool kind, and semantic tags.

### Tool Execution

`tools/call` delegates to the existing `ToolFacadeService.execute()` path and
returns the existing governed tool envelope in MCP `structuredContent`.

The platform can return:

- `completed`
- `approval_required`
- `failed`

Approval is resolved by calling the MCP tool `resolve_confirmation`.

### Resource Read

Resource handles are mapped to MCP resource URIs:

```text
mobiflow://resource/{handle}
```

`resources/read` delegates to the existing resource service for JSON and text
resources. Binary download remains available through the compatibility handle
download endpoint during the migration.

### Audit Query

Audit timeline lookup is exposed as the MCP tool `query_audits`. It delegates to
the existing audit query service.

### Heterogeneous Runs

`create_heterogeneous_run` creates one governed run whose targets may carry
different resolved waypoint sequences and Android profiles. The caller supplies
each dispatch entry as `sequenceId + profilePackage + taskPayload + select`.
`select` is exactly one of a non-empty `deviceIds` selector or a positive `count`
with required/excluded tags. Named devices reserve capacity first; tag selectors
then consume device-id-sorted candidates in dispatch order. Device de-duplication
is guaranteed within one create request, not across concurrently created runs.

This tool accepts already resolved Agent payloads. Sequence catalog lookup and AI
drafting (`resolve_sequence` / `draft_sequence`) remain outside this protocol.
Creation uses normal explicit approval. For mixed profiles the run-level
`profilePackage` is null and the run-level `taskPayload` is `{}`; each target's
current task is authoritative.

The standard P2-3b Agent flow first reads `list_devices` and
`get_run_planning_catalog`, maps a bounded `CollectionIntent` to a typed
`DispatchPlan`, and resolves every complete `.vN` sequence ID from the Agent's
catalog. Its deterministic compiler supplies the full sequence payload and
Platform default run/artifact policy. The resulting underlying
`create_heterogeneous_run` action is submitted through
`propose_governed_action`; a direct `create_heterogeneous_run` adapter call is
not the Agent's standard entry point.

Inventory state used during compilation is advisory. It does not reserve a
device or guarantee tag capacity. After explicit approval, Platform performs
the authoritative identity, availability, de-duplication, and capacity checks
while creating the run. An `approval_required` response therefore means a
confirmation is pending, not that the run has already been created.

The same operation is available to operators as `POST /api/runs/heterogeneous`.

### Waypoint Evidence

`record_waypoint_segments` writes terminal-attempt evidence without driving a
device action. It is audited, replay-safe, annotated idempotent, and does not
require approval. Input segments use the Agent fields
`step_id/behavior_label/entered_at_ms/arrived_at_ms/dwell_ms`; callers cannot
provide device or sequence identity. Platform derives those values through the
trusted `attempt -> task -> run target` relationship.

Segments are stored per attempt as `WAYPOINT_SEGMENT` events. `COMPLETE` has all
three timestamps, `INTERRUPTED` has entered time only, and `INCOMPLETE` has no
timestamps. Interrupted and incomplete segments are not complete pcap windows.
The `(attempt_id,event_key)` key makes equal replays a no-op and rejects changed
payloads. Retries keep independent evidence on their own attempt.

## Compatibility Tool Runtime

`/tools/**` remains available as the internal compatibility protocol and rollback
path:

- `GET /tools/catalog`
- `POST /tools/execute`
- `POST /tools/confirmations/resolve`
- `POST /tools/resources/read`
- `GET /tools/resources/{handle}/download`
- `POST /tools/audits/query`

To roll the Agent back to this path, configure:

```text
PLATFORM_ADAPTER_KIND=http
PLATFORM_TOOL_BASE_URL=http://<control-service>/tools
```

During the migration, the MCP facade reuses `/tools/**` service logic instead of
rewriting business tool implementations.

## Protocol Boundaries

- `/executor/**` serves Android executors only.
- `/api/**` serves the console and operator workflows.
- `/mcp` is the Agent standard protocol.
- `/tools/**` is the Agent compatibility and internal implementation layer.
- AI service `/internal/**` remains exposed only to `control-service`.
