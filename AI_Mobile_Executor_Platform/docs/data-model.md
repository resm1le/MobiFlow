# 数据模型

## 核心对象

### Device

注册过的 Android 终端及其稳定事实，例如设备型号、Android 版本、屏幕信息、已安装 profile 和标签。

### Device Runtime State

设备的可变运行态，包括：

- 在线状态
- 可调度状态
- busy 标记
- 当前 task / attempt 绑定
- 最近心跳
- lease 过期信息
- 最近 command
- 健康快照

### Task

真正被 executor claim 的工作单元。任务可以是独立任务，也可以是 run-backed task。

### Attempt

一次被租约化的执行尝试，由控制面在 claim 时创建，并经历 leased、running、terminal 等状态。

### Device Pool

设备选择规则集合，包括 host group、固定设备、required tags 和 excluded tags。

### Experiment Run

一次 run-first 运行的头对象，保存公共任务形态、device pool、优先级、labels、artifact policy、retry budget 和 queue timeout。异构 run 的 `pool_id` 与 `profile_package` 可以为空，`task_payload_json` 固定为 `{}`；它们不能替代 target 当前 task 的真实执行定义。

### Experiment Run Target

一次 run 中面向单设备的执行槽位，拥有不可变的 nullable `sequence_id`、per-device 状态、retry 计数、当前 task 和最近 attempt。历史同构 target 的 `sequence_id` 保持为空。

### Device Command

控制面对设备下发的运行时动作，例如 cancel、quiesce 或 resume。

### Run Event

一次 attempt 的追加型执行遥测。除 Android executor 事件外，Platform 也把 Agent 的航点时间证据保存为结构化 `WAYPOINT_SEGMENT`：`event_key` 在 attempt 内幂等，`payload_json` 保存原始五字段以及由 Platform 注入的可信 `sequence_id/deviceId`。

### Artifact

执行输出的最终元数据，例如日志、截图和 UI dump。

### Artifact Upload Session

直传 artifact 流中的临时授权与 finalize 状态对象。

### AI Audit Objects

用于保存：

- run planning 请求与结果
- failure triage 结果
- run summary 结果

## 主要表

- `devices`
- `device_runtime_state`
- `device_pools`
- `experiment_runs`
- `experiment_run_targets`
- `tasks`
- `task_attempts`
- `device_commands`
- `run_events`
- `artifacts`
- `artifact_upload_sessions`
- `ai_run_plan_requests`
- `ai_run_plan_results`
- `ai_failure_triage_results`
- `ai_run_summary_results`
- `tool_execution_audits`
- `tool_confirmation_tokens`

## Run-first 关系

- `ExperimentRun` 物化为多个 `ExperimentRunTarget`
- 每个 target 会拥有初始 queued task
- task 在 claim 时创建 attempt
- attempt、run events 和 artifacts 会把 run 关系一路带下去
- `create_single_device_run` 会创建一条单目标 run，并把 task 绑定到指定设备
- `create_heterogeneous_run` 在一次事务中为每个 resolved dispatch assignment 创建 target/task
- target 的 `sequence_id` 与当前 task 的 `task_payload_json` 共同定义该设备的行为；run 头不是异构任务模板
- 失败重试与 queue-timeout 重试从 target 的上一 task 克隆完整 TaskSpec，不回退到 run 头
- waypoint segment 通过 attempt 关联保存，retry 不覆盖上一 attempt 的证据

## Tool Runtime 审计关系

当前 `/tools/**` 会把以下上下文写入审计：

- requestId
- sessionId
- callerContext
- riskLevel
- status
- entityRefs

从而把 Agent step 和平台执行对象串到同一条时间线中。
