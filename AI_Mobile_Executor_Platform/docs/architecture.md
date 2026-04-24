# 架构说明

## 总体结构

当前 Platform 由三部分组成：

- `executor-control-service`
  平台主控制面，也是 canonical state 的唯一来源
- `executor-ai-service`
  结构化 AI 服务，负责 run planning、run summary、failure triage
- `executor-console-web`
  运维和观察控制台，消费 `/api/**`

配套还有：

- `integration`
  启动脚本、验证脚本和示例 payload

## 控制面在架构中的位置

`executor-control-service` 是系统中枢，负责：

- 设备与运行态
- 调度、claim、attempt 创建和状态推进
- run、run target、task 的聚合推进
- command、cancel、resume、quiesce
- artifact metadata
- `/api/**`
- `/executor/**`
- `/tools/**`
- AI 请求上下文构建、AI 结果审计与物化

## AI 服务在架构中的位置

`executor-ai-service` 是受控的结构化 AI 后端。它：

- 只接受 control-service 的内部请求
- 产出结构化 planning / summary / triage 结果
- 不直接接触设备
- 不直接写控制面权威状态

## 控制台在架构中的位置

`executor-console-web` 只消费 `/api/**`，不直接访问设备，也不直接调用 AI 服务。它提供：

- 设备、run、task、attempt 观察界面
- AI 评审流
- 受控 admin 操作

## Agent 接入层在架构中的位置

`/tools/**` 当前是平台面向 Agent 的正式接入层，属于 control-service 的一部分。它不是标准 MCP server，但借鉴了 tool/resource 的语义。当前职责包括：

- tool catalog
- execute
- governed side-effect confirmation
- resource read / download
- audit timeline query

## Android 端在架构中的位置

Android 执行端是被调度的设备 runtime，不参与平台决策。它只做：

- register
- heartbeat
- claim
- execute
- event
- artifact
- finish

## 关键数据流

### 人工或控制台发起

1. operator 通过 `/api/**` 创建 run 或 task
2. control-service 物化出 run、target、task
3. Android 端通过 `/executor/**` claim 并执行
4. 事件和产物回流到 control-service
5. run 聚合状态更新并暴露给控制台

### Agent 发起

1. Agent 通过 `/tools/**` 读取 observation 和 advisory 信息
2. 如需副作用，先发起 execute
3. 平台视风险返回 `completed` 或 `approval_required`
4. 用户确认后，Agent 调用 `confirmations/resolve`
5. control-service 真正落地状态变化
6. 后续执行仍走统一 run-first 链路

### AI 参与

1. control-service 构造 planning / summary / triage 上下文
2. 调用 ai-service
3. ai-service 返回结构化结果
4. control-service 做校验、审计和物化
5. 结果通过 `/api/**` 或 `/tools/**` 被消费

## 当前架构特点

- 平台仍是权威控制面，不把 LLM 嵌进核心状态机
- Agent 通过 `/tools/**` 接入，而不是直接依赖 `/api/**`
- 端侧只负责执行和上报，不承担自治决策
- side-effect 治理由 Platform 服务端掌控
