# 项目总览

## 仓库包含什么

当前仓库是 MobiFlow 的 Platform 控制面实现，包含：

- `services/executor-control-service`
- `services/executor-ai-service`
- `apps/executor-console-web`
- `integration`

当前仓库不包含：

- Agent 源码本体
- Android 执行端源码本体

对应项目位于当前仓库内的 sibling 目录：

- `D:\developing\MobiFlow\AI_Mobile_Executor_Agent`
- `D:\developing\MobiFlow\AutoA11y_Executor`

## 在整个系统中的位置

MobiFlow 可以按三层理解：

- **Platform**
  权威控制面，持有 canonical state 和治理规则
- **Agent**
  受治理的任务型 Agent Runtime，通过 `/tools/**` 消费平台能力
- **Android Executor**
  被调度的设备执行 runtime，通过 `/executor/**` 领取和执行任务

## 当前平台职责

- 设备注册、状态维护和调度治理
- run、run target、task、attempt 状态推进
- command、event、artifact 管理
- AI 规划、总结、诊断的中介、审计和物化
- 面向控制台、执行端和 Agent 的协议提供

## 当前平台能力边界

### `/api/**`

面向控制台与运维操作，提供：

- devices
- device pools
- runs
- tasks
- attempts
- artifact 下载
- AI run plan / run summary / failure triage 评审流

### `/executor/**`

面向 Android 执行端，提供：

- register
- heartbeat
- claim
- start
- events
- finish
- artifact upload / finalize

### `/tools/**`

面向 Agent，当前是 `tool-envelope-v2` 的自定义 tool runtime。它的核心特点是：

- 机器可读 catalog
- 统一 execute envelope
- governed side-effect
- resource handle 模型
- audit query 能力

## 当前设计重点

### Run-first

平台当前以 run-first 作为主执行模型：

- `ExperimentRun`
  一次正式运行
- `ExperimentRunTarget`
  一次 run 中面向单设备的执行槽位
- `Task`
  真正被 executor claim 的工作单元
- `TaskAttempt`
  claim 之后创建的执行尝试

除 pool-based `create_run` 外，平台也通过 `/tools/**` 暴露了 `create_single_device_run`，让 Agent 能表达“让某台设备执行一个任务”，同时仍保持完整 run 链路。

### Governed Tool Runtime

平台不再把 Agent 视为“默认可信且可直接执行一切副作用”的调用方。当前语义是：

- bearer token 仍沿用控制面 admin token
- 尚未引入 per-agent ACL
- 但副作用执行已由 Platform 服务端治理
- execute 可能先返回 `approval_required`
- 真正落地要走 `confirmations/resolve`

### Agent-native Observation

平台已经提供面向 Agent 判断和恢复的 observation/read 工具，包括：

- `get_run_governance_snapshot`
- `get_run_lineage_snapshot`
- `get_attempt_diagnosis_bundle`
- `get_recovery_guidance_context`

这些工具的目标不是替代底层实体查询，而是减少 Agent 自己拼业务状态。
