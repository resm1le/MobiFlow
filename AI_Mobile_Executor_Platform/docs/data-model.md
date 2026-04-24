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

一次 run-first 运行的头对象，保存任务形态、device pool、优先级、labels、artifact policy、retry budget 和 queue timeout。

### Experiment Run Target

一次 run 中面向单设备的执行槽位，拥有 per-device 状态、retry 计数、当前 task 和最近 attempt。

### Device Command

控制面对设备下发的运行时动作，例如 cancel、quiesce 或 resume。

### Run Event

Android 端对一次 attempt 发出的追加型执行遥测。

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

## Tool Runtime 审计关系

当前 `/tools/**` 会把以下上下文写入审计：

- requestId
- sessionId
- callerContext
- riskLevel
- status
- entityRefs

从而把 Agent step 和平台执行对象串到同一条时间线中。
