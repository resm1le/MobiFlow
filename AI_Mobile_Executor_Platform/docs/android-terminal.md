# Android 端联调说明

## 角色

Android 端在 MobiFlow 中是执行 runtime，不是自治 Agent。它负责：

- 向控制面 register 与 heartbeat
- claim 适合自己的任务
- 在设备侧执行场景
- 上报 `start / events / finish`
- 上传并 finalize artifact

它不负责：

- 平台状态推进
- run 或 attempt 创建
- 智能规划
- 替代控制面调度

## 仓库位置

Android 端源码位于当前仓库内：

- `D:\developing\MobiFlow\AutoA11y_Executor`

## 对接方式

Android 端通过 `/executor/**` 与控制面联调。当前关键端点包括：

- `POST /executor/register`
- `POST /executor/heartbeat`
- `POST /executor/tasks/claim`
- `POST /executor/tasks/{attemptId}/start`
- `POST /executor/tasks/{attemptId}/events`
- `POST /executor/tasks/{attemptId}/finish`
- `POST /executor/tasks/{attemptId}/artifacts/uploads`
- `POST /executor/tasks/{attemptId}/artifacts/uploads/{artifactId}/finalize`

## 典型工作流

1. 设备启动后 register 并定时 heartbeat
2. 设备主动 claim 可执行任务
3. 控制面创建 attempt，并把 payload、run config、artifact policy 返回给设备
4. 设备开始执行插件流
5. 设备持续上报事件和产物
6. 设备 finish，控制面推进 attempt、task、run target、run 状态

## 本地联调边界

- Android 端只依赖 `/executor/**`
- 控制台只依赖 `/api/**`
- Agent 只依赖 `/tools/**`

联调时不要跨越这三条边界。
