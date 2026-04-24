# AI Mobile Executor Platform

`AI_Mobile_Executor_Platform` 是 MobiFlow 的权威控制面。它负责持有平台 canonical state，并为控制台、Android 执行端和 Agent 提供正式接入面。

## 当前定位

Platform 负责：

- 设备注册、运行态和调度治理
- task、attempt、run、run target、command、event、artifact 的权威状态
- Android 执行端的 `/executor/**` 协议
- 控制台与运维的 `/api/**` 接口
- Agent 的 `/tools/**` runtime contract
- AI planning、run summary、failure triage 的中介、审计和物化

Platform 不负责：

- 直接实现用户对话
- 在设备侧做智能决策
- 替代 Android 执行器

## 三层协作关系

- `Executor Platform`
  当前仓库主体，负责权威状态、治理、审计和协议
- `Agent Interface`
  位于 `../AI_Mobile_Executor_Agent`，负责对话理解、编排、诊断和恢复建议
- `Android Executor`
  位于 `../AutoA11y_Executor`，负责 register、heartbeat、claim、execute、event、artifact、finish

## 当前正式接口面

- `/api/**`
  面向控制台、运维和管理操作
- `/executor/**`
  面向 Android 执行端
- `/tools/**`
  面向 Agent 的自定义 tool runtime

其中 `/tools/**` 当前已是 `tool-envelope-v2`，并支持：

- catalog 中的 `toolKind / riskLevel / governance / semanticTags`
- execute 中的 `callerContext`
- governed side-effect 的 `approval_required`
- `POST /tools/confirmations/resolve`
- `POST /tools/audits/query`

## 当前能力概览

- run-first 执行模型
- pool-based run 与 single-device run
- artifact ticket / upload / finalize
- AI run planning、run summary、failure triage
- 面向 Agent 的 observation/read 能力，包括：
  - `get_run_governance_snapshot`
  - `get_run_lineage_snapshot`
  - `get_attempt_diagnosis_bundle`
  - `get_recovery_guidance_context`

## 快速启动

### 基础设施

```powershell
docker compose -f services/executor-control-service/docker-compose.local.yml up -d
```

### 平台服务

```powershell
.\integration\scripts\start-control-service.ps1 -AdminAuthToken <admin-token>
.\integration\scripts\start-ai-service.ps1
```

### 控制台

```powershell
.\integration\scripts\start-console-web.ps1 -BearerToken <admin-token>
```

## 测试

```powershell
cd services/executor-control-service
mvn test

cd ..\executor-ai-service
mvn test

cd ..\..\apps\executor-console-web
npm install
npm run test
npm run build
```

## 文档入口

- [文档导航](./docs/README.md)
- [项目总览](./docs/project-overview.md)
- [架构说明](./docs/architecture.md)
- [控制面说明](./docs/control-plane.md)
- [平台协议概览](./docs/protocol.md)
- [Agent 工具接入说明](./docs/agent-tool-server.md)
- [Android 端联调说明](./docs/android-terminal.md)
- [AI 服务说明](./docs/ai-service.md)
- [控制台说明](./docs/console.md)
- [数据模型](./docs/data-model.md)
- [运维与仓库治理](./docs/operations.md)
- [验证指南](./integration/validation.md)
