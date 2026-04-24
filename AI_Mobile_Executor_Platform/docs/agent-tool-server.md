# Agent 工具接入说明

## 文档定位

本文面向接入 Platform 的 Agent 或 Agent Runtime，实现重点是：

- 平台把什么能力作为工具暴露
- Agent 应该调用哪些正式入口
- 当前协议字段和治理语义是什么
- 资源和审计应该如何读取

本文不讨论：

- control-service 内部实现细节
- Android 执行端内部实现
- 历史演进过程

## 接入原则

从 Agent 视角看，Platform 相当于一个自定义 tool runtime：

- 平台不是标准 MCP server
- 平台不追求标准 MCP client 兼容
- 平台通过 `/tools/**` 暴露正式能力
- Agent 不应直接依赖 `/api/**` 或 `/executor/**`

## 当前正式入口

- `GET /tools/catalog`
- `POST /tools/execute`
- `POST /tools/confirmations/resolve`
- `POST /tools/resources/read`
- `GET /tools/resources/{handle}/download`
- `POST /tools/audits/query`

## 协议版本

当前 `/tools/**` 固定使用：

- `tool-envelope-v2`

## Catalog 语义

每个 tool 当前都包含结构化 metadata，至少包括：

- `toolKind`
- `riskLevel`
- `governance.requiresApproval`
- `governance.confirmationMode`
- `semanticTags`

这意味着 Agent 不应再本地硬编码“哪些是 read / analyze / side-effect”，而应直接消费 catalog。

## Execute 语义

execute 请求当前除了 `requestId / sessionId / tool / arguments` 外，还支持：

- `callerContext`

它至少包含：

- `agentTaskId`
- `turnId`
- `stepId`

平台用它补齐跨层 lineage 和审计信息。

## Governed Side Effect

当前副作用工具的工作方式是：

1. Agent 调用 `POST /tools/execute`
2. 如果该动作需要确认，平台返回：
   - `status = approval_required`
   - `confirmation`
   - `audit`
   - `entityRefs`
3. Agent 向用户呈现确认摘要
4. 用户确认后，Agent 调用 `POST /tools/confirmations/resolve`
5. Platform 在服务端校验并真正执行，且只执行一次

平台当前仍沿用 bearer token，但不再以“默认信任 agent、收到副作用请求就立刻执行”的方式工作。

## 当前主要工具面

### Observation / Read

- `list_devices`
- `get_device`
- `get_run`
- `list_attempts`
- `get_attempt`
- `get_attempt_events`
- `get_attempt_artifacts`
- `get_run_governance_snapshot`
- `get_run_lineage_snapshot`
- `get_attempt_diagnosis_bundle`
- `get_recovery_guidance_context`

### Advisory

- `get_run_planning_catalog`
- `draft_run_plan`
- `get_run_plan`
- `generate_run_summary`
- `get_latest_run_summary`
- `get_run_summary`
- `generate_failure_triage`
- `get_latest_failure_triage`
- `get_failure_triage`

### Governed Action

- `create_device_pool`
- `create_task`
- `create_run`
- `create_single_device_run`
- `cancel_task`
- `cancel_run`
- `resume_device`
- `send_device_command`

## Resource 读取

当 tool 结果带有资源句柄时：

1. 文本 / JSON 资源通过 `POST /tools/resources/read`
2. 二进制资源通过 `GET /tools/resources/{handle}/download`

Agent 不应回退到旧的 admin 下载链接。

## 审计与回放

`POST /tools/audits/query` 支持按以下维度查询时间线：

- `sessionId`
- `agentTaskId`
- `turnId`
- `runId`
- `runTargetId`
- `attemptId`

这条能力主要服务：

- replay
- eval
- 调试排障
- 端到端 lineage 追踪
