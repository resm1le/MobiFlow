# 平台协议概览

本文件汇总 Platform 当前三类正式协议：

- Android 执行端使用的 `/executor/**`
- 控制台和运维使用的 `/api/**`
- Agent 使用的 `/tools/**`

## 1. Executor 协议

Android 执行端通过签名的 pull-based HTTP 协议接入控制面。主要端点包括：

- `POST /executor/register`
- `POST /executor/heartbeat`
- `POST /executor/tasks/claim`
- `POST /executor/tasks/{attemptId}/start`
- `POST /executor/tasks/{attemptId}/events`
- `POST /executor/tasks/{attemptId}/finish`
- `POST /executor/tasks/{attemptId}/artifacts/uploads`
- `POST /executor/tasks/{attemptId}/artifacts/uploads/{artifactId}/finalize`

关键语义：

- task 在 claim 时分配
- attempt 由控制面创建
- claim 响应包含 payload、run config 和 artifact policy
- artifact 走 upload ticket / direct upload / finalize 流

## 2. Admin / Operator API

`/api/**` 面向控制台与运维，提供平台管理和观测能力。它不是 Agent 的长期契约。

主要对象包括：

- devices
- device pools
- runs
- tasks
- attempts
- artifacts
- AI run plan
- AI run summary
- AI failure triage

## 3. Agent Tool Runtime

`/tools/**` 是平台面向 Agent 的正式接入层。它是自定义 tool runtime，借鉴 MCP 的 tool/resource 语义，但不追求标准 MCP client 兼容。

### 当前端点

- `GET /tools/catalog`
- `POST /tools/execute`
- `POST /tools/confirmations/resolve`
- `POST /tools/resources/read`
- `GET /tools/resources/{handle}/download`
- `POST /tools/audits/query`

### 鉴权

当前 `/tools/**` 继续使用：

```http
Authorization: Bearer <token>
```

平台当前仍未引入 per-agent ACL，但副作用执行已经由服务端治理。

### Catalog

`GET /tools/catalog` 返回 `tool-envelope-v2`。每个 tool 至少包含：

- `name`
- `title`
- `description`
- `inputSchema`
- `outputSchema`
- `resultMode`
- `stability`
- `toolKind`
- `riskLevel`
- `governance`
- `semanticTags`

### Execute 请求

`POST /tools/execute` 统一字段：

- `version`
- `requestId`
- `sessionId`
- `tool`
- `arguments`
- `callerContext`

`callerContext` 当前至少包含：

- `agentTaskId`
- `turnId`
- `stepId`

### Execute 响应

统一响应字段：

- `version`
- `requestId`
- `sessionId`
- `tool`
- `status`
- `result`
- `warnings`
- `error`
- `audit`
- `entityRefs`
- `confirmation`

### Governed Side Effect

对 read / advisory 工具，平台通常直接返回 `completed`。  
对受治理副作用工具，平台可能先返回：

- `status = approval_required`

这时需要走：

- `POST /tools/confirmations/resolve`

批准后平台才真正执行动作。

### Audit Query

`POST /tools/audits/query` 可按以下维度查询 tool 时间线：

- `sessionId`
- `agentTaskId`
- `turnId`
- `runId`
- `runTargetId`
- `attemptId`

### Resource Handle

artifact 与其他大对象通过 resource handle 暴露：

- 文本 / JSON 资源走 `POST /tools/resources/read`
- 二进制资源走 `GET /tools/resources/{handle}/download`

## 4. 当前 Agent-native Observation Tools

平台当前提供以下 observation/read 能力，供 Agent 优先消费：

- `get_run_governance_snapshot`
- `get_run_lineage_snapshot`
- `get_attempt_diagnosis_bundle`
- `get_recovery_guidance_context`

同时保留底层实体读取和 advisory 工具，例如：

- `get_run`
- `list_attempts`
- `get_attempt`
- `get_attempt_events`
- `get_attempt_artifacts`
- `generate_failure_triage`
- `get_latest_failure_triage`
- `get_failure_triage`

## 5. 协议边界

- `/executor/**` 只服务 Android 执行端
- `/api/**` 只服务控制台和运维
- `/tools/**` 只服务 Agent
- AI service 的 `/internal/**` 只对 control-service 暴露
