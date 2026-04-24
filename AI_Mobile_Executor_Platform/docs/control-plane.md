# 控制面说明

## 角色

`executor-control-service` 是 Platform 的系统中枢，也是平台状态的唯一权威来源。

它负责：

- devices 与 device runtime state
- tasks、attempts、runs、run targets
- commands、events、artifacts
- AI planning / summary / triage 的中介、审计和物化

## 三类接口面

### `/executor/**`

面向 Android 执行端：

- `POST /executor/register`
- `POST /executor/heartbeat`
- `POST /executor/tasks/claim`
- `POST /executor/tasks/{attemptId}/start`
- `POST /executor/tasks/{attemptId}/events`
- `POST /executor/tasks/{attemptId}/finish`
- `POST /executor/tasks/{attemptId}/artifacts/uploads`
- `POST /executor/tasks/{attemptId}/artifacts/uploads/{artifactId}/finalize`

### `/api/**`

面向控制台和运维：

- devices
- device pools
- runs
- tasks
- attempts
- artifact 下载
- AI run plan / run summary / failure triage

### `/tools/**`

面向 Agent：

- `GET /tools/catalog`
- `POST /tools/execute`
- `POST /tools/confirmations/resolve`
- `POST /tools/resources/read`
- `GET /tools/resources/{handle}/download`
- `POST /tools/audits/query`

## Tool Runtime 当前语义

当前 `/tools/**` 使用 `tool-envelope-v2`。核心点如下：

- catalog 中返回 `toolKind / riskLevel / governance / semanticTags`
- execute 支持 `callerContext`
- side-effect 工具可能先返回 `approval_required`
- 真正落地由 `confirmations/resolve` 控制
- 响应中包含 `audit / entityRefs / confirmation / status`

当前仍沿用 bearer token，尚未引入 per-agent ACL；但 side-effect 已由服务端治理，不再是“工具默认直接开放即落地”。

## 核心控制面行为

- queued task 只在 claim 时被分配给 executor
- attempt 只由控制面创建和推进
- run 创建会展开为 run target 和初始 task
- `create_single_device_run` 会创建一条单目标 run，并把初始 task 绑定到指定设备
- cancel、resume、device command 沿用既有控制面语义
- artifact metadata 只在 finalize 成功后正式可见

## 审计与 lineage

当前控制面会保留 tool execution 审计，并支持通过 `/tools/audits/query` 查询时间线。查询维度包括：

- `sessionId`
- `agentTaskId`
- `turnId`
- `runId`
- `runTargetId`
- `attemptId`

这些查询结果可用于：

- Agent replay
- eval
- 运行时排障
- 跨层 lineage 跟踪

## 后台维护任务

当前控制面还负责后台维护逻辑，例如：

- stale lease 清理
- offline device reconcile
- command expiry
- artifact upload session cleanup
- queued-target timeout reconcile
- run-target retry 与 cancellation reconcile

## 不变性要求

- `/tools/**` 不替代 `/api/**`
- tool facade 不绕过 run/task/attempt/device 的状态机
- console 继续只依赖 `/api/**`
- Android 执行端继续只依赖 `/executor/**`
