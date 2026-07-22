# 验证指南

本文件只保留实际验证步骤，不承担长期架构说明。正式边界和治理规则见 [docs/operations.md](../docs/operations.md)。

## 1. 仓库治理检查

在仓库根目录执行：

```powershell
.\integration\scripts\check-repository-governance.ps1
```

该检查用于确认：

- 正式文档仍集中在根 README、`docs/` 和本文件
- 仓库中没有长期保留的历史计划文档
- 正式 Markdown 没有残留已废弃或明显失真的说明

## 2. 本地自动化回归

### Control Service

```powershell
cd services/executor-control-service
mvn test
```

### AI Service

```powershell
cd services/executor-ai-service
mvn test
```

### Console Web

```powershell
cd apps/executor-console-web
npm install
npm run test
npm run build
```

## 3. 本地服务启动

### 基础设施

```powershell
docker compose -f services/executor-control-service/docker-compose.local.yml up -d
```

### 平台服务

```powershell
.\integration\scripts\start-control-service.ps1 -AdminAuthToken <admin-token>
.\integration\scripts\start-ai-service.ps1
.\integration\scripts\start-console-web.ps1 -BearerToken <admin-token>
```

## 4. 原有平台能力回归

确认以下能力未被 `/tools/**` 改造破坏：

- 控制台仍通过 `/api/**` 工作
- `/api/devices`、`/api/runs`、`/api/tasks`、`/api/attempts` 正常可读
- `/api/runs` 仍可创建 pool-based run
- `/api/tasks` 仍可创建兼容任务
- `/api/runs/{runId}/cancel` 与 `/api/tasks/{taskId}/cancel` 仍可执行
- artifact 仍可通过 admin API 下载
- AI run planning、run summary、failure triage 仍可通过 `/api/**` 使用

## 5. Tool Runtime Smoke

### 读取 catalog

```http
GET /tools/catalog
Authorization: Bearer <admin-token>
```

确认：

- 响应版本为 `tool-envelope-v2`
- catalog 中包含 `toolKind / riskLevel / governance / semanticTags`
- `get_run_governance_snapshot`
- `get_run_lineage_snapshot`
- `get_attempt_diagnosis_bundle`
- `get_recovery_guidance_context`

### 基础只读 smoke

调用：

- `list_devices`
- `list_runs`
- `list_tasks`
- `list_attempts`

确认：

- 响应走统一 envelope
- 返回 `status`
- 返回 `audit`
- 返回 `entityRefs`

### Governed side-effect smoke

调用一个副作用工具，例如：

- `create_single_device_run`
- `cancel_run`

确认：

1. 首次 execute 返回 `approval_required`
2. 响应包含 `confirmation`
3. 响应包含 `audit` 和 `entityRefs`
4. 未确认前，不应落地真正副作用
5. 走 `POST /tools/confirmations/resolve` 后，动作才真正执行

### Resource smoke

1. 通过 `get_attempt_artifacts` 获取 artifact 列表
2. 确认 artifact 带 `resource.handle`
3. 对文本或 JSON 调用 `POST /tools/resources/read`
4. 对二进制调用 `GET /tools/resources/{handle}/download`

### Audit query smoke

调用 `POST /tools/audits/query`，确认至少可按以下维度读取时间线：

- `sessionId`
- `runId`
- `attemptId`

## 6. Run-first 闭环验证

### pool-based run

1. 确认设备出现在 `/api/devices`
2. 创建 device pool
3. 创建 smoke run
4. 确认 run 进入 terminal
5. 确认 run、target、task、attempt 链路完整

### single-device run

1. 选择一台已注册且安装目标 profile 的设备
2. 通过 `/tools/**` 发起 `create_single_device_run`
3. 完成 confirmation resolve
4. 确认返回 run 只有一个 target，且 target 绑定指定设备
5. 确认目标设备可以 claim 该 task，非目标设备不能 claim
6. 确认 attempt `start / finish` 后 run target 与 run 聚合状态正确推进

## 7. AI Smoke

### Run Planning

1. 调用 `get_run_planning_catalog`
2. 调用 `draft_run_plan`
3. 调用 `get_run_plan`
4. 调用 `materialize_run_plan`

### Run Summary

1. 对已有 run 调用 `generate_run_summary`
2. 调用 `get_latest_run_summary`
3. 调用 `get_run_summary`

### Failure Triage

1. 选择 failed 或 cancelled 的 run target
2. 调用 `generate_failure_triage`
3. 调用 `get_latest_failure_triage`
4. 调用 `get_failure_triage`

## 8. 真实设备闭环

1. 启动基础设施
2. 启动 control-service，并把 `-MinioEndpoint` 指向设备可达地址
3. 如需 signed executor，追加 `-DeviceId` 和 `-DeviceToken`
4. 启动 ai-service
5. 从 `../AutoA11y_Executor` 启动 Android 执行端
6. 完成一次 pool-based run 或 single-device run
7. 确认 artifact upload / finalize 全链路成功

## 9. P2-3c Mock Executor 闭环（无需真机）

Mock Executor 只验证 Agent 治理、Platform 调度/lineage 和 Executor 协议；它不运行 ADB、Android profile 或任何设备 UI，不能替代最终真机效果验收。

1. 为两个 mock identity 配置独立 HMAC token（脚本不会打印 token）：

   ```powershell
   $env:P2_3C_DEVICE_TOKENS_JSON = '{"dev-7":"<token-7>","dev-9":"<token-9>"}'
   $env:PLATFORM_TOOL_BASE_URL = 'http://127.0.0.1:8080'
   $env:PLATFORM_TOOL_BEARER_TOKEN = '<admin-token>'
   .\integration\scripts\start-control-service.ps1 -AdminAuthToken $env:PLATFORM_TOOL_BEARER_TOKEN
   ```

2. 先运行无批准 smoke；它注册 mock、完成 discovery/proposal，并停在 `approval_required`，不会创建 run：

   ```powershell
   python .\integration\scripts\run-p2-3c-mock-e2e.py
   ```

3. 明确允许创建和执行模拟 run 后，追加 `--approve`：

   ```powershell
   python .\integration\scripts\run-p2-3c-mock-e2e.py --approve
   ```

4. 验收输出必须同时包含 run terminal 状态和两次 `SIMULATED EXECUTOR - NO DEVICE UI EXECUTED` 提示；脚本会断言 pinned sequence、attempt ownership 和每个 attempt 的 waypoint event 数量。

真实设备验证仍按上一节单独进行；本 smoke 通过不代表 WeChat UI 行为已经实现或验证。
