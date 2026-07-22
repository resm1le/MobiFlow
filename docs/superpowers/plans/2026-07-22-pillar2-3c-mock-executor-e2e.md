# P2-3c Mock Executor 端到端执行与 Executor-owned 航点证据 Implementation Plan

> **For agentic workers:** 按任务顺序测试先行；每个任务只提交列出的文件，不跟踪 `MobiFlow_Agent/.venv/`，不要求真机、不新增 WeChat Android profile、不顺带实现 UI/P2-3d/支柱三。

**Goal:** 在不连接真机的前提下，跑通 `Agent governed dispatch → Platform run/target/task → mock Executor register/claim/start/finish → terminal-attempt waypoint evidence → lineage query` 的完整支柱二闭环；生产执行身份和航点证据由 Executor/Platform 协议承载，不把 Platform attempt 生命周期错误注入 Agent TaskGraph。

**Architecture:** 六层。(1) Agent 继续只负责 `CollectionIntent/DispatchPlan`、正式 sequence 解析和 governed proposal，不参与设备侧 attempt 执行。(2) Platform 保持 run/target/task/attempt 与设备绑定的唯一权威。(3) 新增 executor-authenticated 航点段入口，调用方只提交五个设备无关字段，Platform 从 attempt→task→target 派生 runTargetId/deviceId/sequenceId。(4) 提供可签名、可脚本化的 mock Executor，完整模拟 register/heartbeat/claim/start/generic events/finish/waypoint publish，而不模拟 Android UI。(5) 用 mock 的成功、失败重试、重放和伪造身份场景验证 MySQL、租约、pinned claim、per-target payload 和 attempt 级证据隔离。(6) Android 真机只保留为所有控制面搭好后的独立 profile/执行效果验收，不阻塞本计划。

**Tech Stack:** Java 17、Spring Boot、MyBatis、MySQL 8/Testcontainers、Redis、Python 3.11 标准库、MobiFlow Agent HTTP adapter、pytest/unittest、现有 `/executor/**` 与 `/tools/**` 协议。

---

## 0. 现状核实与架构纠偏

### 0.1 已核实地基

- `ClaimedTask` 已返回 `taskId/attemptId/runId/taskType/profilePackage/taskPayload/runConfig/artifactPolicy/priority/labels/source`，mock Executor 不需要从 Agent 获取任何执行身份。
- 异构 task 的 `taskPayload.waypoint_sequence` 已完整携带 `sequence_id/behavior_label/waypoints`，Platform 已校验 entry sequence/profile/payload 一致。
- claim 已按 `target_device_id` 做 pinned selection，并用 MySQL `FOR UPDATE SKIP LOCKED` 处理并发。
- `/executor/register|heartbeat|tasks/claim|start|events|finish` 已支持 HMAC、nonce 防重放和 attempt ownership 校验。
- 普通 executor `RunEvent` 只有 scenario/step/action 索引与扁平 message，没有承载五字段 waypoint segment 的结构化 payload。
- `WaypointTimelineService` 已实现完整序列顺序校验、terminal attempt 限制、可信 lineage join、COMPLETE/INTERRUPTED/INCOMPLETE 状态、`(attempt_id,event_key)` 幂等与冲突检测。
- 现有 `record_waypoint_segments` 是 MCP/tool 入口，要求调用方提供 `runTargetId + attemptId`；它适合兼容和诊断，但不是生产 Executor 的自然入口。
- 当前 Android profile registry 只有 Google Maps/TikTok/Shein，没有 `com.tencent.mm`；因此本阶段不能声称真实执行了 WeChat 行为。
- `ControlMapperIntegrationTest` 已有 MySQL 8.4 Testcontainers、V10/V11 migration、pinned claim 与 `SKIP LOCKED` 地基，但 Docker 不可用时会跳过。
- Platform integration 目录已有 Docker Compose、control-service 启动脚本和验证指南，但没有可复用 mock Executor。

### 0.2 本计划取代的旧假设

历史 P2-3c 文字写作“把 runTargetId/attemptId 带入 TaskGraph 生命周期并自动 publish”。按现已确认的系统边界，此表述不再作为生产架构：

```text
Agent TaskGraph != Android task attempt runtime
```

真实 UI 操作属于：

```text
Platform task → Android Executor → profile plugin → Platform events/artifacts/finish
```

因此：

1. 不给 `TaskSession` 增 `run_target_id/attempt_id`。
2. 不让 `CollectionDispatchService` 轮询并驱动 Platform attempt。
3. 不让 Agent 在 run 创建后伪装 Executor 发布生产 timeline。
4. `ExecutionTraceExporter.waypoint_segments` 保留为 Agent 仿真/诊断能力，不再被视为生产设备证据的唯一来源。
5. 生产 waypoint evidence 从 Executor ingress 进入；Platform 仍负责验证、补全身份并持久化。

### 0.3 定稿决策

1. **不需要真机。** 本阶段所有设备、执行结果、时间戳和失败均由 mock Executor 决定性生成。
2. **不扩展普通 events payload。** 航点段有严格的完整序列、时间组合和幂等语义，使用独立 endpoint，避免把任意 payload 扩散到通用事件协议。
3. **新增 executor endpoint：**

   ```http
   POST /executor/tasks/{attemptId}/waypoint-segments
   ```

4. **请求不接受身份字段。** body 只含 `waypointSegments`，segment 只允许：

   ```text
   step_id / behavior_label / entered_at_ms / arrived_at_ms / dwell_ms
   ```

   `deviceId/sequenceId/runTargetId/taskId/runId` 均由 Platform lineage 派生。
5. **terminal 后发布。** mock 先调用 finish，再调用 waypoint endpoint。这样复用现有 terminal-only 语义；endpoint 本身保持可安全重放。
6. **MCP 入口兼容保留。** `record_waypoint_segments` 不删除；它与 Executor endpoint 复用同一 canonical service，且继续校验显式 runTargetId。
7. **失败重试按 attempt 隔离。** 同一 target 的旧失败 attempt 和新 retry attempt 各自保存独立 `waypoint:0..N`，不能覆盖。
8. **mock 不声称 UI 成功。** mock 的 SUCCESS 只表示控制面协议场景成功；输出和文档统一标记 `simulated_executor`。
9. **签名路径必须覆盖。** 单元测试可使用直接 service mock；端到端 smoke 必须至少有一条 HMAC + Redis nonce 路径，不能只开 unsigned 绕过生产认证。
10. **真机后置。** Android client/DTO、profile 如何将实际页面到达映射为 waypoint、WeChat 插件实现与设备调试另立 P2-3c2，不在本计划暗做。

---

## 1. 对外契约

### 1.1 Executor waypoint ingress

```http
POST /executor/tasks/attempt-123/waypoint-segments
X-Executor-DeviceId: device-7
X-Executor-Protocol-Version: v1
X-Executor-Timestamp: 1780000000000
X-Executor-Nonce: nonce-123
X-Executor-Signature: <hmac>
Content-Type: application/json

{
  "waypointSegments": [
    {
      "step_id": "logged_in",
      "behavior_label": "wechat_text_chat",
      "entered_at_ms": 1780000000100,
      "arrived_at_ms": 1780000000500,
      "dwell_ms": 400
    }
  ]
}
```

响应：

```json
{
  "runTargetId": "target-123",
  "attemptId": "attempt-123",
  "recordedCount": 1
}
```

约束：

- segment 列表必须与 task payload 中正式 sequence 的 waypoint 数量和顺序完全一致。
- `behavior_label` 必须与 sequence 一致。
- 完整 timing → `COMPLETE`；只有 entered → `INTERRUPTED`；三者全空 → `INCOMPLETE`。
- attempt 必须 terminal，且必须属于认证设备。
- 相同 payload 重放返回 200；相同 event key 改内容返回 `409 WAYPOINT_SEGMENT_CONFLICT`。
- body 出现 `deviceId/sequenceId/runTargetId/taskId/runId` 或其他额外字段返回 `400`，不能静默忽略。

### 1.2 Mock Executor 场景

```python
MockExecutorScenario(
    devices=[
        MockDevice("dev-7", profiles=["com.tencent.mm"], tags=["android13"]),
        MockDevice("dev-9", profiles=["com.tencent.mm"], tags=["android13"]),
    ],
    outcome_by_device={
        "dev-7": MockAttemptOutcome.SUCCESS,
        "dev-9": MockAttemptOutcome.FAIL_THEN_SUCCEED,
    },
)
```

mock 必须：

- 使用真实 executor identity JSON。
- 支持与 Android `ExecutorRequestSigner` 相同的 canonical HMAC。
- 为每次请求生成新 nonce。
- 从 claim 响应读取 task/attempt/run/profile/payload，不接受测试代码另行塞入 lineage。
- 从 `waypoint_sequence` 生成完整、顺序一致的模拟 segment 列表。
- 失败 attempt 生成 COMPLETE 前缀 + INTERRUPTED 当前项 + INCOMPLETE 后缀。
- 成功 attempt 生成全部 COMPLETE。

### 1.3 完整验收流

```text
mock register devices
  → Agent list_devices/get_run_planning_catalog
  → CollectionDispatchService.submit_plan
  → approval_required
  → explicit resolve_approval(true)
  → Platform creates heterogeneous run/targets/tasks
  → each mock device claims only its pinned task
  → start + generic event + finish
  → publish waypoint segments as the same authenticated device
  → query lineage/events
  → assert sequence/device/attempt/timing joined correctly
```

---

## 2. 实施任务

### Task 1：定义 Executor waypoint API contract

**Files:**

- Modify: `AI_Mobile_Executor_Platform/services/executor-control-service/src/main/java/com/example/platform/control/api/ExecutorApiModels.java`
- Modify: `AI_Mobile_Executor_Platform/services/executor-control-service/src/test/java/com/example/platform/control/api/ExecutorIngressControllerTest.java`
- Create: `AI_Mobile_Executor_Platform/services/executor-control-service/src/test/resources/contracts/p2-3c-executor-waypoint-segments.json`

- [ ] **Step 1：先写 API schema/JSON 测试**

覆盖：

- 五字段完整 segment 能反序列化。
- INTERRUPTED/INCOMPLETE 的 nullable timing 能反序列化。
- 空 segments、超过 256、空 step/behavior 拒绝。
- segment 含调用方身份字段或未知字段拒绝。
- response 只含 derived `runTargetId/attemptId/recordedCount`。

- [ ] **Step 2：定义严格 request/response records**

推荐：

```java
record ExecutorWaypointSegmentsRequest(
    @NotEmpty @Size(max = 256) List<@Valid ExecutorWaypointSegment> waypointSegments
) {}

record ExecutorWaypointSegment(
    @JsonProperty("step_id") @NotBlank String stepId,
    @JsonProperty("behavior_label") @NotBlank String behaviorLabel,
    @JsonProperty("entered_at_ms") Long enteredAtMs,
    @JsonProperty("arrived_at_ms") Long arrivedAtMs,
    @JsonProperty("dwell_ms") Long dwellMs
) {}
```

为该 request 使用严格未知字段拒绝策略；不要全局修改 ObjectMapper 影响兼容接口。可通过专用 DTO `@JsonIgnoreProperties(ignoreUnknown = false)` + endpoint 显式字段检测实现。

- [ ] **Step 3：运行测试**

```bash
cd AI_Mobile_Executor_Platform/services/executor-control-service
mvn -Dtest=ExecutorIngressControllerTest test
```

- [ ] **Step 4：提交**

```bash
git add AI_Mobile_Executor_Platform/services/executor-control-service/src/main/java/com/example/platform/control/api/ExecutorApiModels.java \
  AI_Mobile_Executor_Platform/services/executor-control-service/src/test/java/com/example/platform/control/api/ExecutorIngressControllerTest.java \
  AI_Mobile_Executor_Platform/services/executor-control-service/src/test/resources/contracts/p2-3c-executor-waypoint-segments.json
git commit -m "feat(platform): define executor waypoint evidence contract"
```

---

### Task 2：让 canonical timeline service 从 attempt 派生 target

**Files:**

- Modify: `AI_Mobile_Executor_Platform/services/executor-control-service/src/main/java/com/example/platform/control/application/WaypointTimelineService.java`
- Modify: `AI_Mobile_Executor_Platform/services/executor-control-service/src/test/java/com/example/platform/control/application/WaypointTimelineServiceTest.java`
- Modify: `AI_Mobile_Executor_Platform/services/executor-control-service/src/main/java/com/example/platform/control/application/ToolFacadeService.java`
- Modify: `AI_Mobile_Executor_Platform/services/executor-control-service/src/test/java/com/example/platform/control/application/ToolFacadeServiceTest.java`

- [ ] **Step 1：先写派生 lineage 测试**

新增入口概念：

```java
recordForAttempt(attemptId, expectedDeviceId, expectedRunTargetId, segments)
```

覆盖：

- `expectedRunTargetId=null` 时从 `attempt.taskId → task.runTargetId` 派生。
- `expectedDeviceId` 不匹配拒绝。
- MCP 传入的 expected runTargetId 不匹配仍拒绝。
- task 没有 runTargetId、target 不存在、attempt/task/target/run/device 任一 lineage 断裂均拒绝。
- terminal-only、sequence order、timing 和 replay/conflict 语义完全保持。

- [ ] **Step 2：重构单一 canonical implementation**

要求：

- Executor endpoint 与 MCP tool 只能调用同一 implementation。
- 不复制 `parseSequence/validateStepOrder/validateTiming/toEvent`。
- Platform 始终覆盖 deviceId/sequenceId，任何调用方都不能提供可信身份。
- 保持事件 key `waypoint:{index}` 与 V11 唯一键，不新增 migration。

- [ ] **Step 3：保持 MCP 兼容**

`record_waypoint_segments(runTargetId, attemptId, ...)` 继续可用，返回 envelope 不变；内部把 runTargetId 作为 expected lineage，而不是权威来源。

- [ ] **Step 4：运行测试**

```bash
cd AI_Mobile_Executor_Platform/services/executor-control-service
mvn -Dtest=WaypointTimelineServiceTest,ToolFacadeServiceTest test
```

- [ ] **Step 5：提交**

```bash
git add AI_Mobile_Executor_Platform/services/executor-control-service/src/main/java/com/example/platform/control/application/WaypointTimelineService.java \
  AI_Mobile_Executor_Platform/services/executor-control-service/src/test/java/com/example/platform/control/application/WaypointTimelineServiceTest.java \
  AI_Mobile_Executor_Platform/services/executor-control-service/src/main/java/com/example/platform/control/application/ToolFacadeService.java \
  AI_Mobile_Executor_Platform/services/executor-control-service/src/test/java/com/example/platform/control/application/ToolFacadeServiceTest.java
git commit -m "refactor(platform): derive waypoint lineage from attempts"
```

---

### Task 3：暴露 executor-authenticated waypoint endpoint

**Files:**

- Modify: `AI_Mobile_Executor_Platform/services/executor-control-service/src/main/java/com/example/platform/control/api/ExecutorIngressController.java`
- Modify: `AI_Mobile_Executor_Platform/services/executor-control-service/src/main/java/com/example/platform/control/application/ControlPlaneService.java`
- Modify: `AI_Mobile_Executor_Platform/services/executor-control-service/src/test/java/com/example/platform/control/api/ExecutorIngressControllerTest.java`
- Modify: `AI_Mobile_Executor_Platform/services/executor-control-service/src/test/java/com/example/platform/control/application/ControlPlaneServiceTest.java`
- Modify: `AI_Mobile_Executor_Platform/services/executor-control-service/src/test/java/com/example/platform/control/api/ExecutorAuthFilterTest.java`

- [ ] **Step 1：先写 ownership 与状态测试**

覆盖：

- owned terminal attempt → 200 + derived response。
- attempt 属于其他 device → `ATTEMPT_DEVICE_MISMATCH`。
- attempt 非 terminal → `WAYPOINT_SEGMENT_INVALID`。
- attempt/task/run 引用伪造 → 对应稳定错误。
- 相同签名 nonce 重放在 auth filter 被拒绝。
- endpoint path 参与签名 canonical string。
- waypoint payload 重放成功；内容冲突返回 409。

- [ ] **Step 2：实现 Controller/ControlPlane facade**

调用顺序：

1. `ExecutorAuthContext.required()`。
2. `AttemptAccessValidator.requireOwnedAttempt()`。
3. 把认证 deviceId 作为 `expectedDeviceId` 传 canonical timeline service。
4. 返回 derived target/attempt/count。

不要信任 body 中的 attempt/device/run 字段；path attemptId 是唯一请求标识。

- [ ] **Step 3：运行测试**

```bash
cd AI_Mobile_Executor_Platform/services/executor-control-service
mvn -Dtest=ExecutorIngressControllerTest,ControlPlaneServiceTest,ExecutorAuthFilterTest test
```

- [ ] **Step 4：提交**

```bash
git add AI_Mobile_Executor_Platform/services/executor-control-service/src/main/java/com/example/platform/control/api/ExecutorIngressController.java \
  AI_Mobile_Executor_Platform/services/executor-control-service/src/main/java/com/example/platform/control/application/ControlPlaneService.java \
  AI_Mobile_Executor_Platform/services/executor-control-service/src/test/java/com/example/platform/control/api/ExecutorIngressControllerTest.java \
  AI_Mobile_Executor_Platform/services/executor-control-service/src/test/java/com/example/platform/control/application/ControlPlaneServiceTest.java \
  AI_Mobile_Executor_Platform/services/executor-control-service/src/test/java/com/example/platform/control/api/ExecutorAuthFilterTest.java
git commit -m "feat(platform): accept executor waypoint evidence"
```

---

### Task 4：实现可签名的 mock Executor 协议客户端

**Files:**

- Create: `AI_Mobile_Executor_Platform/integration/mock_executor/__init__.py`
- Create: `AI_Mobile_Executor_Platform/integration/mock_executor/client.py`
- Create: `AI_Mobile_Executor_Platform/integration/mock_executor/models.py`
- Create: `AI_Mobile_Executor_Platform/integration/mock_executor/scenario.py`
- Create: `AI_Mobile_Executor_Platform/integration/mock_executor/tests/test_client.py`
- Create: `AI_Mobile_Executor_Platform/integration/mock_executor/tests/test_scenario.py`

- [ ] **Step 1：先写纯 Python contract 测试**

无需运行 Platform，使用 fake HTTP transport 覆盖：

- HMAC 与 Java/Kotlin fixed vector 完全相同。
- 每个请求 timestamp/nonce/body hash/path 进入签名。
- register/heartbeat/claim/start/events/finish/waypoint endpoint payload 精确。
- claim 空闲返回 None。
- claim task 保留完整 per-target taskPayload，不做 falsey `or {}` 损坏。
- 成功与失败 segment 生成器严格保持 sequence 顺序。
- mock 不接受外部 runTargetId/deviceId 注入 waypoint body。
- 4xx contract error 不重试；5xx/transport error 标为 retryable，但场景 runner 有有界次数。

- [ ] **Step 2：实现最小 stdlib client**

只用 Python 标准库：`urllib/json/hashlib/hmac/uuid/time`。不要给 Platform 或 Agent 增生产依赖。

接口建议：

```python
client.register(device)
client.heartbeat(device, current_attempt_id=None)
task = client.claim(device)
client.start(task)
client.events(task, events)
client.finish(task, outcome)
client.publish_waypoint_segments(task.attempt_id, segments)
```

- [ ] **Step 3：实现 deterministic scenario runner**

runner 只模拟协议，不调用 ADB、不加载 Android、不声称执行 UI。clock/nonce/outcome 均可注入，测试稳定。

- [ ] **Step 4：运行测试**

```bash
cd AI_Mobile_Executor_Platform
python3 -m unittest discover -s integration/mock_executor/tests -v
```

- [ ] **Step 5：提交**

```bash
git add AI_Mobile_Executor_Platform/integration/mock_executor
git commit -m "test(platform): add signed mock executor client"
```

---

### Task 5：建立 Agent→Platform→mock Executor live smoke

**Files:**

- Create: `AI_Mobile_Executor_Platform/integration/scripts/run-p2-3c-mock-e2e.py`
- Create: `AI_Mobile_Executor_Platform/integration/payloads/p2-3c-mock-scenario.json`
- Modify: `AI_Mobile_Executor_Platform/integration/scripts/start-control-service.ps1`
- Modify: `AI_Mobile_Executor_Platform/integration/validation.md`

- [ ] **Step 1：先定义 fixture 与失败断言**

固定两个 mock devices、两个 sequence dispatch：

- `dev-7 → wechat.text_chat.v1 → success`
- `dev-9 → wechat.video_call.v1 → success`

断言：

- mock 注册前 planning catalog 不虚构 profile；注册后出现 `com.tencent.mm`。
- Agent direct `DispatchPlan` 经 compiler/governance 提交，首次只返回 approval required。
- 明确 approve 后才出现 runId。
- 两台设备只 claim 自己 pinned 的 sequence/profile/payload。
- dev-7 不会 claim dev-9 task，dev-9 也不会 claim dev-7 task。
- 两个 attempts 各有独立 waypoint event 集合。
- run 最终聚合 SUCCESS。
- smoke 输出明确 `SIMULATED EXECUTOR - NO DEVICE UI EXECUTED`。

说明：Platform planning catalog 当前默认 `maxRetriesPerDevice=0`，P2-3b compiler 按设计必须使用该默认值，不能为了测试让 Agent 私自篡改为 1。失败重试在 Task 6 通过显式 `maxRetriesPerDevice=1` 的 Platform integration fixture 验证，与 Agent 默认策略 smoke 分开。

- [ ] **Step 2：实现 live smoke orchestration**

脚本复用：

- `MobiFlow_Agent` 的 `HttpPlatformAdapter`、`CollectionDispatchService.submit_plan()`、`resolve_approval()`。
- Task 4 的 mock Executor client。
- 正式 `SequenceCatalog.default()`，不在 fixture 复制生产 sequence。

配置全部来自参数/环境：

```text
PLATFORM_TOOL_BASE_URL
PLATFORM_TOOL_BEARER_TOKEN
P2_3C_DEVICE_TOKENS_JSON
```

脚本不得自动批准，除非调用者显式传 `--approve`；无该参数时在 approval required 停止并以成功的 prepare-only smoke 退出。

- [ ] **Step 3：支持本地签名设备启动**

`start-control-service.ps1` 增加安全的多 device-token 配置方式，避免只支持单一 `DeviceId/DeviceToken`。不要在日志打印 token。

- [ ] **Step 4：运行无批准 smoke**

```bash
python3 AI_Mobile_Executor_Platform/integration/scripts/run-p2-3c-mock-e2e.py
```

Expected: 注册、discovery、proposal 成功，停在 `approval_required`，无 run。

- [ ] **Step 5：运行显式批准完整 smoke**

```bash
python3 AI_Mobile_Executor_Platform/integration/scripts/run-p2-3c-mock-e2e.py --approve
```

Expected: run terminal、retry lineage 与 waypoint events 全部断言通过。

- [ ] **Step 6：提交**

```bash
git add AI_Mobile_Executor_Platform/integration/scripts/run-p2-3c-mock-e2e.py \
  AI_Mobile_Executor_Platform/integration/payloads/p2-3c-mock-scenario.json \
  AI_Mobile_Executor_Platform/integration/scripts/start-control-service.ps1 \
  AI_Mobile_Executor_Platform/integration/validation.md
git commit -m "test(integration): exercise governed mock executor flow"
```

---

### Task 6：MySQL/Redis、并发与重放发布门

**Files:**

- Modify: `AI_Mobile_Executor_Platform/services/executor-control-service/src/test/java/com/example/platform/control/infrastructure/mapper/ControlMapperIntegrationTest.java`
- Create: `AI_Mobile_Executor_Platform/services/executor-control-service/src/test/java/com/example/platform/control/integration/MockExecutorRunIntegrationTest.java`

- [ ] **Step 1：扩展真实 MySQL mapper 测试**

覆盖：

- V10/V11 migration 实际执行。
- `(attempt_id,event_key)` 同值重放不增加行。
- 不同 payload 同 key 触发冲突且不部分写入。
- retry attempt 相同 `waypoint:0` 不冲突。
- 两个并发 mock claims 不会拿到同一 pinned task。

- [ ] **Step 2：增加 SpringBoot HTTP integration test**

使用：

- `@SpringBootTest(webEnvironment=RANDOM_PORT)`
- MySQL 8.4 Testcontainer
- Redis Testcontainer
- 两个配置 token 的 signed mock identities

通过真实 HTTP 跑 register→claim→start→finish→waypoint，而不是直接调用 mapper。integration fixture 显式设置 `maxRetriesPerDevice=1`，覆盖首次失败、同 target retry 成功及两个 attempt 的独立 evidence；至少覆盖一次 nonce replay 拒绝和 wrong-device ownership 拒绝。

- [ ] **Step 3：运行 Docker gate**

```bash
cd AI_Mobile_Executor_Platform/services/executor-control-service
mvn -Dtest=ControlMapperIntegrationTest,MockExecutorRunIntegrationTest test
```

验收输出必须确认 tests 实际运行；若因 `disabledWithoutDocker` 被跳过，不能报告发布门通过。

- [ ] **Step 4：提交**

```bash
git add AI_Mobile_Executor_Platform/services/executor-control-service/src/test/java/com/example/platform/control/infrastructure/mapper/ControlMapperIntegrationTest.java \
  AI_Mobile_Executor_Platform/services/executor-control-service/src/test/java/com/example/platform/control/integration/MockExecutorRunIntegrationTest.java
git commit -m "test(platform): verify mock executor lineage on mysql"
```

---

### Task 7：文档、总回归与范围检查

**Files:**

- Modify: `docs/superpowers/specs/2026-07-20-pillar2-waypoint-scheduling-design.md`
- Modify: `docs/superpowers/specs/2026-07-20-project-positioning-baseline.md`
- Modify: `AI_Mobile_Executor_Platform/docs/protocol.md`
- Modify: `AI_Mobile_Executor_Platform/docs/operations.md`
- Modify: `AI_Mobile_Executor_Platform/integration/validation.md`
- Modify: `MobiFlow_Agent/README.md`

- [ ] **Step 1：纠正生产执行边界**

文档明确：

- Agent 负责意图、计划、sequence 解析、governed proposal。
- Platform 负责调度、审批、lineage、状态和证据落库。
- Executor 负责 attempt 执行及事件/产物/航点证据回传。
- mock Executor 是协议与控制面验证，不是真实 UI 行为验证。
- 不再把 Platform attempt 注入 Agent TaskGraph 作为 P2-3c 生产方案。

- [ ] **Step 2：运行 Platform 全量**

```bash
cd AI_Mobile_Executor_Platform/services/executor-control-service
mvn test
```

- [ ] **Step 3：运行 mock client tests**

```bash
cd AI_Mobile_Executor_Platform
python3 -m unittest discover -s integration/mock_executor/tests -v
```

- [ ] **Step 4：运行 Agent 全量**

```bash
cd MobiFlow_Agent
pytest -q
```

- [ ] **Step 5：运行显式批准 live smoke**

在 Docker Compose + control-service 环境执行 Task 5 完整 smoke，并保存命令输出摘要；不能用 service mock 替代此发布门。

- [ ] **Step 6：范围检查**

```bash
git status --short
git diff --check
rg -n "run_target_id|attempt_id|record_waypoint_segments" MobiFlow_Agent/mobiflow_agent/collection MobiFlow_Agent/mobiflow_agent/task
rg -n "adb|uiautomator|com.tencent.mm" AI_Mobile_Executor_Platform/integration/mock_executor
```

Expected:

- Agent collection/task 没有新增 Platform attempt 生命周期字段。
- mock 没有 ADB/UI 调用，`com.tencent.mm` 只作为声明的模拟 profile identity。
- 没有 Android plugin/真机代码改动。
- 没有 Console UI/P2-3d 改动。
- `.venv/` 未跟踪。

- [ ] **Step 7：提交**

```bash
git add docs/superpowers/specs/2026-07-20-pillar2-waypoint-scheduling-design.md \
  docs/superpowers/specs/2026-07-20-project-positioning-baseline.md \
  AI_Mobile_Executor_Platform/docs/protocol.md \
  AI_Mobile_Executor_Platform/docs/operations.md \
  AI_Mobile_Executor_Platform/integration/validation.md \
  MobiFlow_Agent/README.md
git commit -m "docs: define executor-owned waypoint evidence flow"
```

---

## 3. 验收矩阵

| 能力 | 正向验收 | 失败/边界验收 |
|---|---|---|
| execution ownership | Executor claim 得到完整 task identity/payload | Agent 不持有 attempt lifecycle |
| executor auth | signed request + fresh nonce 成功 | 错签名、旧 timestamp、nonce replay 拒绝 |
| pinned dispatch | 每个 mock device 只 claim 自己 target | 两设备并发不重复 claim |
| per-target payload | text/video target 各自 sequence/profile/payload | retry 不回退 run-level 空 payload |
| waypoint ingress | terminal owned attempt 可发布 | running/wrong-device/伪造 identity 拒绝 |
| lineage join | Platform 派生 target/device/sequence | body 不接受 identity 字段 |
| timing | COMPLETE/INTERRUPTED/INCOMPLETE 正确 | 非法时间组合拒绝且不部分写 |
| replay | 同 payload 幂等 | 同 key 改 payload 返回冲突 |
| retry | 每个 attempt 独立 timeline | 旧 attempt 不被新 retry 覆盖 |
| governance | 未批准无 run，批准后创建 | smoke 默认不自动批准 |
| storage | MySQL V10/V11 与唯一键实际验证 | Docker skip 不算发布门通过 |
| scope | mock 完整控制面闭环 | 无真机、ADB、Android profile、UI |

---

## 4. Definition of Done

- Agent→Platform→mock Executor 的成功链路，以及 Platform→mock Executor 的失败重试链路，能在本地 Docker 环境验证。
- 真机完全不参与自动回归，mock 使用和 Android Executor 相同的 `/executor/**` 身份、签名与状态协议。
- Executor waypoint endpoint 不接受调用方 device/sequence/target/run identity。
- Platform 从 attempt→task→target 派生并验证所有 lineage。
- MCP `record_waypoint_segments` 保持兼容且与 Executor ingress 共用 canonical service。
- waypoint evidence 只在 terminal attempt 接受，重放幂等、冲突拒绝、retry attempt 隔离。
- 两个 mock devices 能领取异构 pinned tasks，且 claim payload 与 Agent 正式 catalog 编译结果一致。
- approval required 不被当成 run 已创建；live smoke 只有显式 `--approve` 才执行副作用。
- MySQL/Redis Testcontainers gate 实际运行，无被 skip 的发布门伪通过。
- Platform、mock client、Agent 全量测试通过。
- 设计文档明确 Executor-owned production lifecycle，不再要求 Agent TaskGraph 注入 Platform attempt。

---

## 5. 明确后置

- **P2-3c2 真机 Executor 适配：** Android DTO/client 调 waypoint endpoint，profile/engine 把真实页面到达映射为 semantic waypoint，断网本地重放，单机与多机真机 smoke。
- **WeChat profile：** `com.tencent.mm` 的实际场景、页面签名、账号/联系人 fixture 与稳定性调试。
- **Artifact live smoke：** MinIO ticket/upload/finalize 可作为独立发布门；不与 waypoint endpoint 实现耦合。
- **P2-3d：** sequence/behavior/attempt timeline UI、异构创建和 confirmation 交互、草稿人工入库。
- **复杂 NL 与 reservation：** 自动选最优设备、跨 run 独占和容量优化。
- **支柱三/四：** rendezvous barrier、跨设备同步、动作级时间线与更细 pcap 对齐。
