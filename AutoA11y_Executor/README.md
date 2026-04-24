# AutoA11y_Executor

`AutoA11y_Executor` 是 MobiFlow 中的 Android 端执行 runtime。

它的职责刻意保持收敛：

- 作为 Android 执行器和设备侧 runtime
- 负责 register、heartbeat、claim、execute、event、artifact、finish
- 执行来自 Platform 的已分配任务
- 把执行过程中的健康状态、事件和产物回传给平台

它不是：

- 平台控制面
- Agent
- 自主决策系统

## 当前长期模块

- `executor-app`
- `executor-control`
- `executor-reporting`
- `core`
- `engine`
- `drivers`
- `env`
- `monitor`
- `shared`
- `plugins/scenarios-googlemaps`
- `plugins/scenarios-tiktok`
- `plugins/scenarios-shein`

## 执行链

当前 Android 端的主执行链可概括为：

`TaskExecutionService -> TimeBoxedRunner -> ScenarioExecutor -> DriverChain -> concrete drivers -> plugin flow`

也就是：

1. 从控制面领到任务
2. 在本地进入带时间盒的执行流程
3. 场景执行器调用底层驱动链
4. 进入具体插件场景
5. 在执行过程中不断上报事件和上传产物
6. 最终回报成功或失败

## 对接协议

Android 端通过平台 `/executor/**` 接口完成：

- 设备注册
- 心跳
- 任务领取
- 开始执行
- 事件上报
- 结束回报
- 产物上传与 finalize

## 文档入口

- Android 文档导航：[docs/README.md](./docs/README.md)
- Platform 文档入口：[../AI_Mobile_Executor_Platform/docs/README.md](../AI_Mobile_Executor_Platform/docs/README.md)
