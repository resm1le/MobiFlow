# P2-2 Platform 异构分派与航点时间线 Join Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Platform 能在一个 `ExperimentRun` 内把不同的、已解析的 `WaypointSequence` 精确分派给不同设备，并把 Agent 的设备无关 `waypoint_segments` 作为结构化证据落库，由 Platform 注入可信 `deviceId`，形成可与第三方 pcap 对齐的设备航点时间线。

**Architecture:** 八步。(1) 用兼容迁移给 run target 增 `sequence_id`，并允许异构 run 的 run 级 `profile_package` 为空；真实执行定义仍保存在每个 `TaskEntity`。(2) 新增“已解析序列 + selector”请求契约和确定性设备分配器，先处理点名设备，再按 dispatch 顺序分配标签候选。(3) `ExperimentRunService` 在所有校验/选址成功后一次性创建 run/targets/tasks；初始 task 使用 entry 自己的 payload，重试从该 target 的上一 task 克隆，绝不回退到 run 级模板。(4) 暴露 Admin API 与受显式确认保护的 `create_heterogeneous_run` MCP 工具。(5) 扩展 `run_events` 保存结构化 `WAYPOINT_SEGMENT`，以 attempt 为粒度保留重试历史。(6) 新增无人工确认、但完整审计和幂等的 `record_waypoint_segments` MCP 证据上报工具；Platform 通过 `attempt → task → target` 注入 `deviceId/sequenceId`。(7) 更新 Agent MCP 适配器及既有 Java/TypeScript/Python 响应模型的兼容映射。(8) 用固定 P2-1d fixture 做契约闭环，并完成 Java、Python、MCP 与 MySQL/Testcontainers 回归。

**Tech Stack:** Java 17、Spring Boot 3.3、MyBatis、Flyway、MySQL 8、JUnit 5、Mockito、Testcontainers、Python 3.11、pydantic v2、pytest、TypeScript/Vitest。

---

## 0. 现状核实与本计划定稿决策

### 0.1 已核实的现有地基

- `TaskEntity.taskPayloadJson` 已是 per-task 字段，claim 也从 task 读取 payload；`tasks` 表无需新增 payload 列。
- `ExperimentRunTargetEntity` 尚无 `sequenceId`；最新 Flyway 迁移是 V9，新增迁移从 V10 开始。
- `createInitialTargetTask` 和 `queueNextTargetTask` 都仍从 run 复制共享 TaskSpec；两处都必须改。
- `ExperimentRunSelectors.matchesPool` 已过滤 registered/online/QUIESCED，但未过滤 `busy`。
- claim 已使用 `target_device_id` + `FOR UPDATE SKIP LOCKED`，租约、续租和 reaper 不改。
- P2-1d 当前真实输出为：

```json
{
  "step_id": "logged_in",
  "behavior_label": "wechat_text_chat",
  "entered_at_ms": 1000,
  "arrived_at_ms": 1500,
  "dwell_ms": 500
}
```

- P2-1d 尚未输出设计草案曾提到的 `verdict`、`path_action_count`；P2-2 不虚构这两个字段。
- Platform 当前没有接收 Agent `waypoint_segments` 的结构化通道；只改 target 或 trace response 不能完成 join。

### 0.2 对总体设计的必要细化

1. **P2-2 的 `create_heterogeneous_run` 接收 Agent 已解析的序列 payload。** 当前仓库没有 sequence catalog。工具仅收 `sequence_id` 无法生成 target task；因此 entry 必须同时携带 `sequenceId + profilePackage + taskPayload`，Platform 校验三者一致。确定性的 `resolve_sequence`、AI `draft_sequence`、`IntentPlanner/DispatchPlan` 均留 P2-3。
2. **允许跨 App 真异构。** 一个 run 可含不同 `profilePackage`；run 级 `profile_package` 在所有 entry 相同时保留该值，否则为 `NULL`。run 级 `task_payload_json` 对异构 run 固定为 `{}`；真实 payload 只看 target 当前 task。
3. **公共执行策略保持 run 级。** P2-2 首版要求同一异构 run 共用 `taskType`、`runConfig`、`artifactPolicy`、`priority`、`labels`、`source`、`createdBy`、retry/queue timeout；entry 只变化 sequence、profile、payload 和 selector。
4. **设备去重只保证单次 create 请求内。** 点名优先、标签 entry 按原顺序占位。P2-2 不新增跨 run 设备 reservation；claim/lease 仍保证同一时刻不重复执行，但两个并发 create 请求可能为同一空闲设备各排一个 pinned task。
5. **航点时间线通过 Agent-facing MCP 上报。** 不冒充 executor，也不把 deviceId 放进 Agent trace。`record_waypoint_segments` 是证据写入，不驱动设备动作，因此不要求人工确认；仍必须写 tool audit，并支持 request replay。
6. **查询复用 attempt events。** 每段保存为 `WAYPOINT_SEGMENT` run event；现有 `get_attempt_events`/Admin attempt events 增加结构化 `payload` 即可，不在 run target response 内重复聚合时间线。

---

## 1. 对外契约

### 1.1 `create_heterogeneous_run` MCP 输入

MCP 保持现有 camelCase 风格。`taskPayload` 必须是 Agent 已解析的 envelope，至少含非空 `goal` 和完整 `waypoint_sequence`：

```json
{
  "name": "collection-batch-01",
  "description": "wechat mixed collection",
  "taskType": "PLUGIN_RUN",
  "runConfig": {
    "loopCount": 1,
    "budgetMs": 300000,
    "loopIntervalMs": 0,
    "networkIsolationEnabled": false,
    "pollIntervalMs": 15000,
    "heartbeatIntervalMs": 30000
  },
  "artifactPolicy": {
    "uploadLog": true,
    "uploadScreenshot": true,
    "uploadDump": true
  },
  "priority": 100,
  "labels": ["pcap"],
  "source": "agent",
  "createdBy": "mobiflow-agent",
  "maxRetriesPerDevice": 1,
  "queueTimeoutMs": 300000,
  "dispatch": [
    {
      "sequenceId": "wechat.text_chat.v1",
      "profilePackage": "com.tencent.mm",
      "taskPayload": {
        "goal": "Run wechat.text_chat.v1",
        "waypoint_sequence": {
          "sequence_id": "wechat.text_chat.v1",
          "behavior_label": "wechat_text_chat",
          "profile_package": "com.tencent.mm",
          "waypoints": [
            {
              "waypoint_id": "logged_in",
              "description": "Reach the logged-in home screen.",
              "arrival_spec": {
                "verification_id": "verify:logged_in",
                "target_kind": "task",
                "target_id": "logged_in",
                "success_checks": [
                  {
                    "check_id": "logged-in-visible",
                    "description": "The logged-in home screen is visible."
                  }
                ]
              }
            }
          ]
        }
      },
      "select": {
        "count": 3,
        "requiredTags": ["android13"],
        "excludedTags": ["unstable"]
      }
    },
    {
      "sequenceId": "wechat.video_call.v1",
      "profilePackage": "com.tencent.mm",
      "taskPayload": {
        "goal": "Run wechat.video_call.v1",
        "waypoint_sequence": {
          "sequence_id": "wechat.video_call.v1",
          "behavior_label": "wechat_video_call",
          "profile_package": "com.tencent.mm",
          "waypoints": [
            {
              "waypoint_id": "call_connected",
              "description": "Reach the connected video-call screen.",
              "arrival_spec": {
                "verification_id": "verify:call_connected",
                "target_kind": "task",
                "target_id": "call_connected",
                "success_checks": [
                  {
                    "check_id": "call-connected-visible",
                    "description": "The connected call screen is visible."
                  }
                ]
              }
            }
          ]
        }
      },
      "select": {"deviceIds": ["dev-7", "dev-9"]}
    }
  ]
}
```

Selector 严格二选一：

- 点名模式：`deviceIds` 非空；`count/requiredTags/excludedTags` 必须为空。
- 标签模式：`count > 0`；`deviceIds` 必须为空；tags 可为空。

### 1.2 `record_waypoint_segments` MCP 输入

segment 五字段原样复用 P2-1d snake_case；调用方不能传 `deviceId` 或 `sequenceId`：

```json
{
  "runTargetId": "target-1",
  "attemptId": "attempt-1",
  "waypointSegments": [
    {
      "step_id": "logged_in",
      "behavior_label": "wechat_text_chat",
      "entered_at_ms": 1000,
      "arrived_at_ms": 1500,
      "dwell_ms": 500
    }
  ]
}
```

Platform canonical payload：

```json
{
  "sequence_id": "wechat.text_chat.v1",
  "step_id": "logged_in",
  "behavior_label": "wechat_text_chat",
  "deviceId": "dev-7",
  "entered_at_ms": 1000,
  "arrived_at_ms": 1500,
  "dwell_ms": 500
}
```

成功输出固定为：

```json
{
  "runTargetId": "target-1",
  "attemptId": "attempt-1",
  "events": [
    {
      "eventType": "WAYPOINT_SEGMENT",
      "state": "COMPLETE",
      "payload": {
        "sequence_id": "wechat.text_chat.v1",
        "step_id": "logged_in",
        "behavior_label": "wechat_text_chat",
        "deviceId": "dev-7",
        "entered_at_ms": 1000,
        "arrived_at_ms": 1500,
        "dwell_ms": 500
      }
    }
  ]
}
```

`runTargetId/attemptId` 是 tool entity refs 的稳定来源；Agent adapter 对外方法只返回 `events` 列表。

---

## 2. Global Constraints

- 不改 `TaskMapper.findClaimableQueuedTasks`、lease、renew、reaper 的并发机制。
- 不改 Kotlin executor；Agent 证据通过 MCP 上报，不复用 executor bearer 身份。
- 不实现 `IntentPlanner`、`DispatchPlan`、`resolve_sequence`、`draft_sequence` 或 UI；这些属于 P2-3。
- 不新增复杂序列库；Platform 只验证 resolved payload 的 identity 与最小可执行核心，不声称完整复刻 Pydantic schema。调用方负责先用 Agent `WaypointSequence` 完整校验；可选字段若不合法，仍由 Agent 的权威 schema 在执行边界拒绝。
- 不把 `deviceId` 注入 Agent `TaskSession` 或 `ExecutionTraceExporter`。
- 不把异构 run 的第一条 profile/payload 冒充整个 run 的公共真值。
- 历史 homogeneous target 的 `sequence_id` 保持 `NULL`，不伪造回填。
- `record_waypoint_segments` 不接受 device identity；deviceId 只从 Platform 持久化关系取得。
- `record_waypoint_segments` 只接受已进入终态的 attempt；运行中 attempt 必须先 finish，避免 incomplete 证据占用不可变幂等键后阻塞最终 trace。
- 每次 attempt 独立保存 timeline；retry 不覆盖旧 attempt 证据。
- 完成 segment：三个时间字段都非空，且 `entered >= 0`、`arrived >= entered`、`dwell == arrived - entered`，保存为 `COMPLETE`。
- 中断 segment：只允许 `entered_at_ms` 非空而 `arrived_at_ms/dwell_ms` 都为空，保存为 `INTERRUPTED`；它表示步骤已激活但未到达，不能作为 pcap 完整时间窗。
- 未执行 segment：三个时间字段全部为 `null`，保存为 `INCOMPLETE`，也不能作为 pcap 时间窗。
- 其它部分时间组合、未知/重复/乱序 step、label 不匹配、负时长、超过 256 段全部拒绝。
- 同一 `(attempt_id, event_key)` 相同 payload 重报为 no-op；不同 payload 返回结构化 conflict，禁止覆盖。
- 所有 Java 命令显式使用 JDK 17；本机默认 `java` 是 Java 8，裸跑 Maven 会失败。
- MySQL/Flyway/`SKIP LOCKED` 验收必须在 Docker 可用环境运行；`disabledWithoutDocker` 导致的 skip 不能被当作 SQL 已验证。

---

## 3. File Structure

### Platform — Modify

- `services/executor-control-service/src/main/java/com/example/platform/control/domain/PersistenceModels.java`
- `services/executor-control-service/src/main/java/com/example/platform/control/infrastructure/mapper/ExperimentRunTargetMapper.java`
- `services/executor-control-service/src/main/java/com/example/platform/control/infrastructure/mapper/TaskAttemptMapper.java`
- `services/executor-control-service/src/main/java/com/example/platform/control/infrastructure/mapper/RunEventMapper.java`
- `services/executor-control-service/src/main/java/com/example/platform/control/api/AdminApiModels.java`
- `services/executor-control-service/src/main/java/com/example/platform/control/api/AdminRunController.java`
- `services/executor-control-service/src/main/java/com/example/platform/control/application/ControlErrorCode.java`
- `services/executor-control-service/src/main/java/com/example/platform/control/application/ExperimentRunSelectors.java`
- `services/executor-control-service/src/main/java/com/example/platform/control/application/ExperimentRunService.java`
- `services/executor-control-service/src/main/java/com/example/platform/control/application/ToolFacadeService.java`
- `services/executor-control-service/src/main/java/com/example/platform/control/application/McpFacadeService.java`
- `services/executor-control-service/src/main/java/com/example/platform/control/application/AdminApiService.java`
- `services/executor-control-service/src/test/java/com/example/platform/control/application/ExperimentRunServiceTest.java`
- `services/executor-control-service/src/test/java/com/example/platform/control/application/ToolFacadeServiceTest.java`
- `services/executor-control-service/src/test/java/com/example/platform/control/application/McpFacadeServiceTest.java`
- `services/executor-control-service/src/test/java/com/example/platform/control/application/AdminApiServiceTest.java`
- `services/executor-control-service/src/test/java/com/example/platform/control/infrastructure/mapper/ControlMapperIntegrationTest.java`
- `AI_Mobile_Executor_Platform/docs/protocol.md`
- `AI_Mobile_Executor_Platform/docs/data-model.md`

### Platform — Create

- `services/executor-control-service/src/main/resources/db/migration/V10__heterogeneous_run_targets.sql`
- `services/executor-control-service/src/main/resources/db/migration/V11__waypoint_segment_events.sql`
- `services/executor-control-service/src/main/java/com/example/platform/control/application/HeterogeneousDispatchResolver.java`
- `services/executor-control-service/src/main/java/com/example/platform/control/application/WaypointTimelineService.java`
- `services/executor-control-service/src/test/java/com/example/platform/control/application/ExperimentRunSelectorsTest.java`
- `services/executor-control-service/src/test/java/com/example/platform/control/application/HeterogeneousDispatchResolverTest.java`
- `services/executor-control-service/src/test/java/com/example/platform/control/application/WaypointTimelineServiceTest.java`
- `services/executor-control-service/src/test/java/com/example/platform/control/api/AdminRunControllerTest.java`
- `services/executor-control-service/src/test/resources/contracts/p2-2-resolved-sequence.json`
- `services/executor-control-service/src/test/resources/contracts/p2-1d-waypoint-segments.json`

### Agent / Console compatibility — Modify

- `MobiFlow_Agent/mobiflow_agent/platform/types.py`
- `MobiFlow_Agent/mobiflow_agent/platform/adapter/mapping.py`
- `MobiFlow_Agent/mobiflow_agent/platform/adapter/mcp.py`
- `MobiFlow_Agent/tests/platform/test_platform_adapter.py`
- `MobiFlow_Agent/tests/waypoint/test_platform_sequence_contract.py`
- `AI_Mobile_Executor_Platform/apps/executor-console-web/src/lib/types.ts`
- `AI_Mobile_Executor_Platform/apps/executor-console-web/src/routes/runs-page.tsx`
- `AI_Mobile_Executor_Platform/apps/executor-console-web/src/routes/run-detail-page.tsx`
- 对应现有 Vitest 页面测试。

---

## Task 1: V10 — target sequenceId 与异构 run 聚合兼容

**Files:**

- Create: `.../db/migration/V10__heterogeneous_run_targets.sql`
- Modify: `.../domain/PersistenceModels.java`
- Modify: `.../infrastructure/mapper/ExperimentRunTargetMapper.java`
- Modify: `.../api/AdminApiModels.java`
- Modify: `.../application/ExperimentRunService.java`
- Test: `.../infrastructure/mapper/ControlMapperIntegrationTest.java`

**Interfaces:**

- `ExperimentRunTargetEntity.sequenceId: String | null`
- `ExperimentRunTargetResponse.sequenceId: String | null`
- `ExperimentRunSummaryResponse.profilePackage` 允许 `null`

- [ ] **Step 1: 写失败的 mapper/response 测试**

在 `ControlMapperIntegrationTest` 增加：新 target 的 `sequenceId` insert/read round-trip；旧 target `sequenceId=null` 仍可读。服务测试增加 target response 暴露 sequenceId。

- [ ] **Step 2: 运行确认失败**

```bash
JAVA_HOME=/Library/Java/JavaVirtualMachines/temurin-17.jdk/Contents/Home \
  /Library/Java/JavaVirtualMachines/temurin-17.jdk/Contents/Home/bin/java -version
JAVA_HOME=/Library/Java/JavaVirtualMachines/temurin-17.jdk/Contents/Home \
  mvn -f AI_Mobile_Executor_Platform/services/executor-control-service/pom.xml \
  -Dtest=ControlMapperIntegrationTest,ExperimentRunServiceTest test
```

Expected: entity/mapper 尚无 `sequenceId`，测试编译或断言失败。

- [ ] **Step 3: 新增 V10 迁移**

```sql
ALTER TABLE experiment_run_targets
    ADD COLUMN sequence_id varchar(255) DEFAULT NULL AFTER device_id,
    ADD KEY idx_run_targets_run_sequence (run_id, sequence_id);

ALTER TABLE experiment_runs
    MODIFY COLUMN profile_package varchar(255) DEFAULT NULL;
```

不修改历史 V3；`sequence_id` nullable 以兼容历史 target 和旧 API。

- [ ] **Step 4: 更新 entity 与 mapper 的所有列清单**

`ExperimentRunTargetMapper` 的 insert 以及 `findById`、`lockById`、`findByRunId`、`findPendingQueueTargets` 四个 select 全部加入 `sequence_id`。`update` 不更新 sequenceId，使其创建后不可变。

- [ ] **Step 5: 更新响应映射**

`ExperimentRunTargetResponse` 和 `toTargetResponse` 增 nullable `sequenceId`。此步只改 Java DTO；MCP schema/Agent/Console 兼容在 Task 4/7 完成。

- [ ] **Step 6: 运行测试与 diff 检查**

```bash
JAVA_HOME=/Library/Java/JavaVirtualMachines/temurin-17.jdk/Contents/Home \
  mvn -f AI_Mobile_Executor_Platform/services/executor-control-service/pom.xml \
  -Dtest=ExperimentRunServiceTest,ControlMapperIntegrationTest test
git diff --check
```

- [ ] **Step 7: 提交**

```bash
git add AI_Mobile_Executor_Platform/services/executor-control-service/src/main/resources/db/migration/V10__heterogeneous_run_targets.sql \
  AI_Mobile_Executor_Platform/services/executor-control-service/src/main/java/com/example/platform/control/domain/PersistenceModels.java \
  AI_Mobile_Executor_Platform/services/executor-control-service/src/main/java/com/example/platform/control/infrastructure/mapper/ExperimentRunTargetMapper.java \
  AI_Mobile_Executor_Platform/services/executor-control-service/src/main/java/com/example/platform/control/api/AdminApiModels.java \
  AI_Mobile_Executor_Platform/services/executor-control-service/src/main/java/com/example/platform/control/application/ExperimentRunService.java \
  AI_Mobile_Executor_Platform/services/executor-control-service/src/test/java/com/example/platform/control/application/ExperimentRunServiceTest.java \
  AI_Mobile_Executor_Platform/services/executor-control-service/src/test/java/com/example/platform/control/infrastructure/mapper/ControlMapperIntegrationTest.java
git commit -m "feat(platform): persist sequence identity per run target"
```

---

## Task 2: resolved dispatch 契约与确定性设备分配器

**Files:**

- Modify: `.../api/AdminApiModels.java`
- Modify: `.../application/ControlErrorCode.java`
- Modify: `.../application/ExperimentRunSelectors.java`
- Create: `.../application/HeterogeneousDispatchResolver.java`
- Create: `.../application/ExperimentRunSelectorsTest.java`
- Create: `.../application/HeterogeneousDispatchResolverTest.java`
- Create: `.../test/resources/contracts/p2-2-resolved-sequence.json`
- Create: `MobiFlow_Agent/tests/waypoint/test_platform_sequence_contract.py`

**Interfaces:**

```java
record CreateHeterogeneousRunRequest(
        String name,
        String description,
        String taskType,
        RunConfig runConfig,
        ArtifactPolicy artifactPolicy,
        Integer priority,
        List<String> labels,
        String source,
        String createdBy,
        Integer maxRetriesPerDevice,
        Long queueTimeoutMs,
        List<HeterogeneousDispatchEntry> dispatch) {}

record HeterogeneousDispatchEntry(
        String sequenceId,
        String profilePackage,
        Map<String, Object> taskPayload,
        DeviceSelector select) {}

record DeviceSelector(
        Integer count,
        List<String> deviceIds,
        List<String> requiredTags,
        List<String> excludedTags) {}
```

- [ ] **Step 1: 写 selector 与 resolver 失败测试**

至少覆盖：

- busy/offline/unregistered/QUIESCED/缺 profile 被排除；
- selector XOR；
- 点名 entry 即使排在标签 entry 后也优先占位；
- 点名 vs 点名冲突拒绝；
- 标签 vs 标签按 dispatch 原顺序占位；
- count 精确且候选按 `deviceId` 排序；
- 容量不足整单失败；
- entry 的 `sequenceId/profilePackage` 与 `taskPayload.waypoint_sequence` 不一致时拒绝；
- payload 必须含 `goal`，sequence 必须含非空 `behavior_label/profile_package` 和非空 waypoints；waypoint ID 唯一，每个 waypoint 必须含非空 `description` 和可执行的 `arrival_spec`（verification id、target kind/id、至少一个含 check id/description 的 success check）。

Platform 在本任务中验证上述可执行核心和 entry/sequence 一致性；Agent `WaypointSequence` 仍是完整 schema 权威。把完整合法 sequence 固定为 `p2-2-resolved-sequence.json`：Java resolver 测试读取它，Python `test_platform_sequence_contract.py` 从同一仓库路径读取并调用 `WaypointSequence.model_validate`，防止两个实现悄然漂移。

- [ ] **Step 2: 运行确认失败**

```bash
JAVA_HOME=/Library/Java/JavaVirtualMachines/temurin-17.jdk/Contents/Home \
  mvn -f AI_Mobile_Executor_Platform/services/executor-control-service/pom.xml \
  -Dtest=ExperimentRunSelectorsTest,HeterogeneousDispatchResolverTest test
```

- [ ] **Step 3: 收紧公共 pool 过滤**

`ExperimentRunSelectors.matchesPool` 在现有 registered/online/QUIESCED 条件中加入 `runtime.isBusy()`；旧 `create_run` 从此也不会把 busy 设备纳入新 run。

- [ ] **Step 4: 实现全量预校验与两阶段分配**

Resolver 一次读取 device/runtime 快照，先规范化所有 TaskSpec，再分配：

1. 处理全部点名 entry，验证 device 存在且 eligible，并加入 `reservedDeviceIds`。
2. 按原 dispatch 顺序处理标签 entry，从排过序且未 reserved 的候选中取恰好 `count` 台。
3. 输出仍按原 dispatch 顺序组织 `ResolvedDispatchEntry`，每个 assignment 含 `sequenceId + normalizedTask + deviceId`。
4. 任何失败发生在写 run 之前。

- [ ] **Step 5: 增加结构化错误码**

至少新增：

- `HETEROGENEOUS_RUN_INVALID`
- `DISPATCH_SELECTOR_INVALID`
- `DISPATCH_DEVICE_UNAVAILABLE`
- `DISPATCH_CAPACITY_INSUFFICIENT`
- `DISPATCH_DEVICE_CONFLICT`

- [ ] **Step 6: 运行定向测试**

```bash
JAVA_HOME=/Library/Java/JavaVirtualMachines/temurin-17.jdk/Contents/Home \
  mvn -f AI_Mobile_Executor_Platform/services/executor-control-service/pom.xml \
  -Dtest=ExperimentRunSelectorsTest,HeterogeneousDispatchResolverTest,ExperimentRunServiceTest test
/opt/homebrew/opt/python@3.11/bin/python3.11 -m pytest \
  MobiFlow_Agent/tests/waypoint/test_platform_sequence_contract.py -q
```

- [ ] **Step 7: 提交**

```bash
git add AI_Mobile_Executor_Platform/services/executor-control-service/src/main/java/com/example/platform/control/api/AdminApiModels.java \
  AI_Mobile_Executor_Platform/services/executor-control-service/src/main/java/com/example/platform/control/application/ControlErrorCode.java \
  AI_Mobile_Executor_Platform/services/executor-control-service/src/main/java/com/example/platform/control/application/ExperimentRunSelectors.java \
  AI_Mobile_Executor_Platform/services/executor-control-service/src/main/java/com/example/platform/control/application/HeterogeneousDispatchResolver.java \
  AI_Mobile_Executor_Platform/services/executor-control-service/src/test/java/com/example/platform/control/application/ExperimentRunSelectorsTest.java \
  AI_Mobile_Executor_Platform/services/executor-control-service/src/test/java/com/example/platform/control/application/HeterogeneousDispatchResolverTest.java \
  AI_Mobile_Executor_Platform/services/executor-control-service/src/test/resources/contracts/p2-2-resolved-sequence.json \
  MobiFlow_Agent/tests/waypoint/test_platform_sequence_contract.py
git commit -m "feat(platform): resolve deterministic heterogeneous dispatch assignments"
```

---

## Task 3: 创建异构 run，并保证重试不退化为同构

**Files:**

- Modify: `.../application/ExperimentRunService.java`
- Modify: `.../application/ExperimentRunServiceTest.java`

**Interfaces:**

- `ExperimentRunService.createHeterogeneousRun(CreateHeterogeneousRunRequest)`
- `createInitialTargetTask(run, resolvedAssignment, now)`
- `queueNextTargetTask(run, target, previousTask, ordinal, now)`

- [ ] **Step 1: 写 3×X + 2×Y 失败测试**

构造 5 台 eligible 设备，断言：

- 一个 run 有 5 targets/tasks；
- X 的 3 个 target 带 X sequence/payload，Y 的 2 个 target 带 Y sequence/payload；
- 设备无重复；
- task 的 `profilePackage` 与对应 entry 一致；
- mixed profiles 时 run response 的 `profilePackage == null`；
- run detail 的公共 `taskPayload == {}`。

- [ ] **Step 2: 写两条重试回归测试**

分别覆盖：

- `onAttemptFinished` 失败重试；
- `reconcileQueuedTimeouts` queue timeout 重试。

新 task 必须从 `previousTask` 克隆 `taskType/profilePackage/taskPayloadJson/runConfigJson/artifactPolicyJson/priority/labelsJson/source/createdBy`，只更新 identity/status/time 字段。

- [ ] **Step 3: 运行确认失败**

```bash
JAVA_HOME=/Library/Java/JavaVirtualMachines/temurin-17.jdk/Contents/Home \
  mvn -f AI_Mobile_Executor_Platform/services/executor-control-service/pom.xml \
  -Dtest=ExperimentRunServiceTest test
```

- [ ] **Step 4: 实现事务创建**

`createHeterogeneousRun` 顺序固定为：规范化公共策略 → resolver 完成全部 assignments → 创建 run → 创建 targets/tasks → 返回 detail。不能在 resolver 成功前 insert run。

异构 run entity：

- `taskType`: 公共 taskType；
- `profilePackage`: assignments 的 profile 全相同时为该值，否则 `null`；
- `taskPayloadJson`: `{}`；
- 其它策略字段使用公共 normalized 配置；
- `poolId`: `null`。

- [ ] **Step 5: 重构初始与重试 task 来源**

旧 homogeneous `createRun/createSingleDeviceRun` 行为保持不变，但可统一包装成 `TargetTaskSpec`。重试严禁再读取 `run.getTaskPayloadJson()` 或 `run.getProfilePackage()`。

- [ ] **Step 6: 测试失败原子性和旧 API 兼容**

容量不足、重复点名、非法 payload 时验证 `experimentRunMapper.insert`、target insert、task insert 均未调用。原有 `createRun` 与 `createSingleDeviceRun` 测试保持通过，历史 target 的 sequenceId 为 null。

- [ ] **Step 7: 运行定向与全量 Java 单测**

```bash
JAVA_HOME=/Library/Java/JavaVirtualMachines/temurin-17.jdk/Contents/Home \
  mvn -f AI_Mobile_Executor_Platform/services/executor-control-service/pom.xml \
  -Dtest=ExperimentRunServiceTest,HeterogeneousDispatchResolverTest test
JAVA_HOME=/Library/Java/JavaVirtualMachines/temurin-17.jdk/Contents/Home \
  mvn -f AI_Mobile_Executor_Platform/services/executor-control-service/pom.xml test
```

- [ ] **Step 8: 提交**

```bash
git add AI_Mobile_Executor_Platform/services/executor-control-service/src/main/java/com/example/platform/control/application/ExperimentRunService.java \
  AI_Mobile_Executor_Platform/services/executor-control-service/src/test/java/com/example/platform/control/application/ExperimentRunServiceTest.java
git commit -m "feat(platform): create per-target heterogeneous run tasks"
```

---

## Task 4: Admin API 与受治理的 create_heterogeneous_run MCP 工具

**Files:**

- Modify: `.../api/AdminRunController.java`
- Create: `.../api/AdminRunControllerTest.java`
- Modify: `.../application/ToolFacadeService.java`
- Modify: `.../application/ToolFacadeServiceTest.java`
- Modify: `.../application/McpFacadeServiceTest.java`
- Modify: relevant API controller tests

- [ ] **Step 1: 写 API/MCP 失败测试**

覆盖：

- `POST /api/runs/heterogeneous` 映射到 service；
- tool catalog 含 `create_heterogeneous_run`；
- input schema 精确表达 dispatch array 与 selector 字段；
- `toolKind=side_effect`、`riskLevel=EXECUTION`、`requiresApproval=true`；
- 首次 call 只返回 `approval_required`，不创建 run；
- approve 后只执行一次并回传 run entity refs；
- malformed selector 返回结构化 tool error；
- `tools/list` 自动暴露新工具。

- [ ] **Step 2: 更新 tool output schema**

`runTargetSchema` 增 nullable `sequenceId`；`runSummarySchema.profilePackage` 改 nullable。`runDetail.taskPayload` 对异构 run 仍是对象 `{}`。

- [ ] **Step 3: 注册工具**

复用现有 `definition(... RISK_EXECUTION ...)`，因此自动进入 explicit confirmation，不另造 token 或 audit 机制。

- [ ] **Step 4: 运行定向测试**

```bash
JAVA_HOME=/Library/Java/JavaVirtualMachines/temurin-17.jdk/Contents/Home \
  mvn -f AI_Mobile_Executor_Platform/services/executor-control-service/pom.xml \
  -Dtest=ToolFacadeServiceTest,McpFacadeServiceTest,AdminRunControllerTest test
```

- [ ] **Step 5: 提交**

```bash
git add AI_Mobile_Executor_Platform/services/executor-control-service/src/main/java/com/example/platform/control/api/AdminRunController.java \
  AI_Mobile_Executor_Platform/services/executor-control-service/src/main/java/com/example/platform/control/application/ToolFacadeService.java \
  AI_Mobile_Executor_Platform/services/executor-control-service/src/test/java/com/example/platform/control/api/AdminRunControllerTest.java \
  AI_Mobile_Executor_Platform/services/executor-control-service/src/test/java/com/example/platform/control/application/ToolFacadeServiceTest.java \
  AI_Mobile_Executor_Platform/services/executor-control-service/src/test/java/com/example/platform/control/application/McpFacadeServiceTest.java
git commit -m "feat(platform): expose governed heterogeneous run creation"
```

---

## Task 5: V11 — 结构化 WAYPOINT_SEGMENT 事件持久化

**Files:**

- Create: `.../db/migration/V11__waypoint_segment_events.sql`
- Modify: `.../domain/PersistenceModels.java`
- Modify: `.../infrastructure/mapper/TaskAttemptMapper.java`
- Modify: `.../infrastructure/mapper/RunEventMapper.java`
- Modify: `.../api/AdminApiModels.java`
- Modify: `.../application/AdminApiService.java`
- Create: `.../application/WaypointTimelineService.java`
- Create: `.../application/WaypointTimelineServiceTest.java`
- Modify: `.../infrastructure/mapper/ControlMapperIntegrationTest.java`
- Create: `.../test/resources/contracts/p2-1d-waypoint-segments.json`

**Persistence shape:**

```sql
ALTER TABLE run_events
    ADD COLUMN event_key varchar(320) DEFAULT NULL AFTER event_type,
    ADD COLUMN payload_json json DEFAULT NULL AFTER message,
    ADD UNIQUE KEY uk_run_events_attempt_event_key (attempt_id, event_key);
```

普通事件的 `event_key=NULL`，MySQL 允许多行 NULL，不改变旧 events 行为。segment 使用 `event_key='waypoint:' + planIndex`，避免依赖 step ID 长度。

- [ ] **Step 1: 写 fixture 驱动的失败测试**

fixture 直接使用 P2-1d 五字段。测试服务通过 `attempt → task → target` 解析：

- task/runTarget/attempt 关系一致；
- target sequenceId 与 task payload sequence 一致；
- 输入 step 列表与 payload waypoints 顺序完全一致；
- canonical payload 的 deviceId 取 target/attempt；
- 每段映射为 `eventType=WAYPOINT_SEGMENT`、`scenarioId=sequenceId`、`stepIndex=planIndex`、`state=COMPLETE|INTERRUPTED|INCOMPLETE`；
- `ts` 依次取 arrived、entered、Platform 接收时间中的首个可用值。

完整 `RunEventEntity` 映射不得遗漏现有非空列：`attemptId/taskId/deviceId/runId` 全部取 trusted lineage，`actionIndex=null`，`code=null`，`message="waypoint_segment:" + planIndex + ":" + state`（稳定且非空），其余字段按上面的 event 映射赋值。fixture 与 mapper 测试必须断言 `message` 非空并可成功 insert。

- [ ] **Step 2: 写非法与幂等测试**

覆盖运行中 attempt、时间逆序、dwell 不匹配、arrived-only、dwell-only、entered+dwell without arrived 等非法部分时间组合、未知/重复/乱序 step、label 不匹配、超过 256 段、伪造 device 字段、attempt/target 不匹配。另有正例证明 entered-only 保存为 `INTERRUPTED`。运行中 attempt 必须拒绝；终态 attempt 同 payload 重报 no-op，不同 payload conflict。

服务输入 record 的五个 segment 字段用 `@JsonProperty` 绑定 P2-1d 的 snake_case 名称，避免依赖全局 Jackson naming policy。

- [ ] **Step 3: 新增 V11、entity 与 mapper 字段**

`RunEventEntity` 新增 `eventKey/payloadJson`；insert、batch provider、所有 select 列清单同步。新增按 `(attemptId,eventKey)` 查询或批量查询接口，供幂等比较使用。

- [ ] **Step 4: 实现不可覆盖的保存算法**

推荐流程：

1. 规范化完整 canonical events；
2. 在同一事务内通过新增的 `TaskAttemptMapper.lockById(attemptId)`（`SELECT ... FOR UPDATE`）锁定 attempt，并确认其已终态；
3. 读取同 attempt 已有 event keys；
4. 已存在且 canonical payload 相同 → 跳过；
5. 已存在但不同 → `WAYPOINT_SEGMENT_CONFLICT`；
6. 对其余 events 使用不覆盖内容的 MySQL upsert（`ON DUPLICATE KEY UPDATE event_key=event_key`）；
7. 重新读取本批全部 keys，逐项解析并比较 canonical payload；相同即成功，不同则抛 `WAYPOINT_SEGMENT_CONFLICT` 并回滚。

不能在同一事务中依赖“捕获 `DuplicateKeyException` 后继续查询”，因为 SQL 异常可能使事务不可继续。attempt 行锁负责串行化正常 service 写入；unique key + no-mutation upsert + post-read comparison 负责兜住 request replay 和意外并发写入。

- [ ] **Step 5: 扩展查询 response**

`RunEventResponse` 增 `Map<String,Object> payload`；`AdminApiService` 把 `payloadJson` 解析为 map。旧事件返回 `payload=null`。现有 `/api/attempts/{attemptId}/events` 不换路径。

- [ ] **Step 6: 运行单元与 mapper 测试**

```bash
JAVA_HOME=/Library/Java/JavaVirtualMachines/temurin-17.jdk/Contents/Home \
  mvn -f AI_Mobile_Executor_Platform/services/executor-control-service/pom.xml \
  -Dtest=WaypointTimelineServiceTest,AdminApiServiceTest,ControlMapperIntegrationTest test
```

Docker 可用时断言 `ControlMapperIntegrationTest` 没有被 skip，验证 JSON round-trip、唯一键、普通 NULL event_key 多行兼容，并验证 `lockById` 能串行化同一 attempt 的并发写入而不阻塞不同 attempt。

- [ ] **Step 7: 提交**

```bash
git add AI_Mobile_Executor_Platform/services/executor-control-service/src/main/resources/db/migration/V11__waypoint_segment_events.sql \
  AI_Mobile_Executor_Platform/services/executor-control-service/src/main/java/com/example/platform/control/domain/PersistenceModels.java \
  AI_Mobile_Executor_Platform/services/executor-control-service/src/main/java/com/example/platform/control/infrastructure/mapper/TaskAttemptMapper.java \
  AI_Mobile_Executor_Platform/services/executor-control-service/src/main/java/com/example/platform/control/infrastructure/mapper/RunEventMapper.java \
  AI_Mobile_Executor_Platform/services/executor-control-service/src/main/java/com/example/platform/control/api/AdminApiModels.java \
  AI_Mobile_Executor_Platform/services/executor-control-service/src/main/java/com/example/platform/control/application/AdminApiService.java \
  AI_Mobile_Executor_Platform/services/executor-control-service/src/main/java/com/example/platform/control/application/WaypointTimelineService.java \
  AI_Mobile_Executor_Platform/services/executor-control-service/src/test/java/com/example/platform/control/application/WaypointTimelineServiceTest.java \
  AI_Mobile_Executor_Platform/services/executor-control-service/src/test/java/com/example/platform/control/application/AdminApiServiceTest.java \
  AI_Mobile_Executor_Platform/services/executor-control-service/src/test/java/com/example/platform/control/infrastructure/mapper/ControlMapperIntegrationTest.java \
  AI_Mobile_Executor_Platform/services/executor-control-service/src/test/resources/contracts/p2-1d-waypoint-segments.json
git commit -m "feat(platform): persist canonical waypoint segment events"
```

---

## Task 6: MCP 证据上报与查询契约

**Files:**

- Modify: `.../application/ToolFacadeService.java`
- Modify: `.../application/McpFacadeService.java`
- Modify: `.../application/ToolFacadeServiceTest.java`
- Modify: `.../application/McpFacadeServiceTest.java`

**Interfaces:**

- `record_waypoint_segments(runTargetId, attemptId, waypointSegments)`
- 现有 `get_attempt_events` 输出 schema 增 nullable `payload`

- [ ] **Step 1: 写治理语义失败测试**

`record_waypoint_segments` 必须：

- 出现在 tool catalog；
- `toolKind=side_effect`，但 `requiresApproval=false`；
- 使用 `ADVISORY` 风险和 `evidence/lineage/idempotent` semantic tags；
- tool call 直接完成、写 tool audit；
- 相同 `requestId` replay 返回已存 response，不重复保存；
- output/entity refs 含 runTargetId/attemptId；
- output 精确为 `{runTargetId, attemptId, events}`，而不是裸 segment 列表；
- MCP 标准 annotation 的 `idempotentHint=true`，同时其它 execution side-effect 仍为 false；
- MCP `tools/call` 能传递 snake_case segment 字段。

- [ ] **Step 2: 为 evidence write 增专用 definition helper**

不要复用会自动要求确认的 `definition(... RISK_EXECUTION ...)`。新增窄 helper，明确：

- `toolKind=side_effect`
- `riskLevel=ADVISORY`
- `requiresApproval=false`
- `resultMode=inline`
- stable

这不是放宽所有 side-effect；只用于不可驱动设备动作、幂等、受 lineage 校验的证据写入。

同步修改 `McpFacadeService.toMcpTool`：当 definition 的 semantic tags 含 `idempotent` 时导出 `idempotentHint=true`，否则保留现有 side-effect=false 规则。补 `tools/list` 断言，避免 `_meta` 和标准 annotations 自相矛盾。

- [ ] **Step 3: 注册 record/query schema**

segment schema 使用精确属性：`step_id/behavior_label/entered_at_ms/arrived_at_ms/dwell_ms`，并 `additionalProperties=false`，从 schema 层拒绝 device identity。

`runEventSchema` 增 nullable map `payload`，现有 `get_attempt_events` 自动返回 joined canonical event。

`record_waypoint_segments` output schema 明确定义必填 `runTargetId`、`attemptId`、`events`；这样现有 entity-ref 提取能看到两个 ID，Agent adapter 再从 completed response 的 `events` 字段返回列表。

- [ ] **Step 4: 运行 Tool/MCP 回归**

```bash
JAVA_HOME=/Library/Java/JavaVirtualMachines/temurin-17.jdk/Contents/Home \
  mvn -f AI_Mobile_Executor_Platform/services/executor-control-service/pom.xml \
  -Dtest=ToolFacadeServiceTest,McpFacadeServiceTest,WaypointTimelineServiceTest test
```

- [ ] **Step 5: 提交**

```bash
git add AI_Mobile_Executor_Platform/services/executor-control-service/src/main/java/com/example/platform/control/application/ToolFacadeService.java \
  AI_Mobile_Executor_Platform/services/executor-control-service/src/main/java/com/example/platform/control/application/McpFacadeService.java \
  AI_Mobile_Executor_Platform/services/executor-control-service/src/test/java/com/example/platform/control/application/ToolFacadeServiceTest.java \
  AI_Mobile_Executor_Platform/services/executor-control-service/src/test/java/com/example/platform/control/application/McpFacadeServiceTest.java
git commit -m "feat(platform): ingest waypoint timelines through audited MCP"
```

---

## Task 7: Agent MCP bridge 与现有客户端兼容

**Files:**

- Modify: `MobiFlow_Agent/mobiflow_agent/platform/types.py`
- Modify: `MobiFlow_Agent/mobiflow_agent/platform/adapter/mapping.py`
- Modify: `MobiFlow_Agent/mobiflow_agent/platform/adapter/mcp.py`
- Modify: `MobiFlow_Agent/tests/platform/test_platform_adapter.py`
- Modify: `AI_Mobile_Executor_Platform/apps/executor-console-web/src/lib/types.ts`
- Modify: run list/detail routes and tests only as needed for nullable display

- [ ] **Step 1: 写 Agent adapter 失败测试**

给 `McpPlatformAdapter` 增公开方法：

```python
def record_waypoint_segments(
    self,
    *,
    run_target_id: str,
    attempt_id: str,
    waypoint_segments: list[dict[str, Any]],
    caller_context: CallerContext,
) -> list[dict[str, Any]]:
    ...
```

测试它把 `ExecutionTraceExporter.export_json(session)["waypoint_segments"]` 原样放进 `record_waypoint_segments` 工具参数，不添加 deviceId，并正确解析 completed response。

completed response 必须先校验顶层 `runTargetId/attemptId` 与请求一致，再只返回其中的 `events`；缺字段、ID 不一致或非列表 events 都作为 Platform contract error，不静默接受。

- [ ] **Step 2: 更新 Agent 响应类型**

- `RunSummaryContext.profile_package: str | None`
- `RunTargetContext.sequence_id: str | None`
- mapping 使用 `.get(...)`，保证历史 homogeneous 和新 heterogeneous response 都能读取。

不在此任务中让 `TaskGraphRuntime` 自动上报；调用方必须显式提供 runTargetId/attemptId。自动生命周期编排随 P2-3 的 DispatchPlan 上下文接入。

- [ ] **Step 3: 更新 Console 兼容类型**

只做既有页面不崩的兼容：

- `ExperimentRunSummary.poolId/profilePackage` 允许 null；
- `ExperimentRunTarget.sequenceId` 允许 null；
- run list/detail 对 null profile 显示 `mixed`/`—`。

不新增异构创建 UI 或 timeline UI。

- [ ] **Step 4: 运行 Python 与前端定向测试**

```bash
cd MobiFlow_Agent
/opt/homebrew/opt/python@3.11/bin/python3.11 -m pytest tests/platform/test_platform_adapter.py \
  tests/runtime/test_trace_export_waypoint_segments.py -q

cd ../AI_Mobile_Executor_Platform/apps/executor-console-web
npm test
```

- [ ] **Step 5: 提交**

```bash
git add MobiFlow_Agent/mobiflow_agent/platform/types.py \
  MobiFlow_Agent/mobiflow_agent/platform/adapter/mapping.py \
  MobiFlow_Agent/mobiflow_agent/platform/adapter/mcp.py \
  MobiFlow_Agent/tests/platform/test_platform_adapter.py \
  AI_Mobile_Executor_Platform/apps/executor-console-web/src/lib/types.ts \
  AI_Mobile_Executor_Platform/apps/executor-console-web/src/routes/runs-page.tsx \
  AI_Mobile_Executor_Platform/apps/executor-console-web/src/routes/run-detail-page.tsx \
  AI_Mobile_Executor_Platform/apps/executor-console-web/src/test/runs-page.test.tsx \
  AI_Mobile_Executor_Platform/apps/executor-console-web/src/test/run-detail-page.test.tsx
git commit -m "feat(agent): publish waypoint segments to platform MCP"
```

---

## Task 8: 契约闭环、文档与全量验收

**Files:**

- Modify: `AI_Mobile_Executor_Platform/docs/protocol.md`
- Modify: `AI_Mobile_Executor_Platform/docs/data-model.md`
- Modify: `AI_Mobile_Executor_Platform/services/executor-control-service/src/test/java/com/example/platform/control/application/ToolFacadeServiceTest.java`
- Modify: `AI_Mobile_Executor_Platform/services/executor-control-service/src/test/java/com/example/platform/control/application/McpFacadeServiceTest.java`
- Modify: `AI_Mobile_Executor_Platform/services/executor-control-service/src/test/java/com/example/platform/control/infrastructure/mapper/ControlMapperIntegrationTest.java`

- [ ] **Step 1: 增加固定跨层契约测试**

同一份 `p2-1d-waypoint-segments.json` 至少经过：

1. Java DTO/tool arguments 解析；
2. `WaypointTimelineService` 校验与 trusted join；
3. `RunEventMapper` JSON 持久化；
4. Admin/MCP `get_attempt_events` 返回；
5. 断言最终 payload 仅多出 Platform 的 `sequence_id/deviceId`，五个 Agent 原始字段不变。

- [ ] **Step 2: 验证异构 claim 不串任务**

Testcontainers 建两种 sequence 的 pinned tasks，两个设备分别 claim，断言各自拿到正确 profile/payload。保留并运行现有 `SKIP LOCKED` 并发测试；不另造租约实现。

- [ ] **Step 3: 更新协议和数据模型文档**

文档必须写清：

- create tool 收 resolved payload，resolve/draft 留 P2-3；
- selector 优先级与单请求去重边界；
- run 级 profile/payload 的聚合语义；
- target.sequenceId 与 task payload 的权威关系；
- record tool 不接受 deviceId、无需人工确认但完整审计；
- `WAYPOINT_SEGMENT` event 的 canonical payload、幂等键、retry 保留策略；
- `INTERRUPTED`（entered-only）与 `INCOMPLETE`（全 null）都不能作为 pcap 完整时间窗。

- [ ] **Step 4: Java 全量测试**

```bash
JAVA_HOME=/Library/Java/JavaVirtualMachines/temurin-17.jdk/Contents/Home \
  mvn -f AI_Mobile_Executor_Platform/services/executor-control-service/pom.xml test
```

基线核实时为 128 tests passed、10 skipped（Docker 不可用）。最终验收要求：

- unit/API/MCP tests 全绿；
- Docker 可用环境下 `ControlMapperIntegrationTest` 实际执行，migration/unique key/JSON/claim 测试 0 skipped。

- [ ] **Step 5: Agent 全量测试**

```bash
cd MobiFlow_Agent
/opt/homebrew/opt/python@3.11/bin/python3.11 -m pytest -q
```

- [ ] **Step 6: Console 全量测试与构建**

```bash
cd AI_Mobile_Executor_Platform/apps/executor-console-web
npm test
npm run build
```

- [ ] **Step 7: 仓库最终检查**

```bash
cd /Users/dengqiuhan.1/code/MobiFlow
git diff --check
git status --short
```

不得 stage/commit `MobiFlow_Agent/.venv/` 或其它用户未跟踪文件。

- [ ] **Step 8: 独立 review**

独立 reviewer 重点检查：

- 重试两条路径是否还读 run payload；
- mixed profile 是否被第一条 entry 冒充；
- 点名是否真的先于标签占位；
- mapper 每个 select 是否都含 `sequence_id/event_key/payload_json`；
- record tool 是否能被伪 deviceId 污染；
- 幂等 replay 与 conflict 是否覆盖 terminal attempt；
- Docker skip 是否被误报为 SQL 已验证；
- P2-3 范围是否被意外提前实现。

- [ ] **Step 9: 提交**

```bash
git add AI_Mobile_Executor_Platform/docs/protocol.md \
  AI_Mobile_Executor_Platform/docs/data-model.md \
  AI_Mobile_Executor_Platform/services/executor-control-service/src/test/java/com/example/platform/control/application/ToolFacadeServiceTest.java \
  AI_Mobile_Executor_Platform/services/executor-control-service/src/test/java/com/example/platform/control/application/McpFacadeServiceTest.java \
  AI_Mobile_Executor_Platform/services/executor-control-service/src/test/java/com/example/platform/control/infrastructure/mapper/ControlMapperIntegrationTest.java
git commit -m "docs(platform): document heterogeneous dispatch and waypoint evidence"
```

---

## 4. Definition of Done

- 一个 run 可创建至少两种 sequence、不同 profile/payload 的 targets/tasks。
- `3×X + 2×Y` 精确生成 5 个无重复 target，点名优先，标签 count 精确。
- busy/offline/unregistered/QUIESCED/缺 profile 设备不会被分配。
- 任一 dispatch 非法或容量不足时不留下 run/target/task 半成品。
- 首轮、失败重试、queue-timeout 重试都保持 target 自己的 TaskSpec。
- 旧 `create_run/create_single_device_run`、历史 target 和普通 run events 保持兼容。
- `create_heterogeneous_run` 必须显式确认；`record_waypoint_segments` 无需确认但有 audit 与幂等保护。
- Platform 不接受调用方 deviceId，最终 event payload 的 deviceId 来自 attempt/target。
- P2-1d 五字段完整 round-trip；`COMPLETE/INTERRUPTED/INCOMPLETE` 与非法时间组合都有测试。
- retry 的每次 attempt 保留独立 timeline，不覆盖旧证据。
- Admin/MCP 能查询结构化 joined event。
- Java、Python、Console 测试全绿；Docker 环境实际验证 V10/V11 与 MySQL 并发/唯一键。

---

## 5. 后续计划（不在 P2-2 范围）

- **P2-3a:** Agent `SequenceCatalog` + `resolve_sequence`（确定性只读）与 `draft_sequence`（AI/intake 草稿）。
- **P2-3b:** `CollectionIntent → IntentPlanner → DispatchPlan`，编译期验证后调用 `create_heterogeneous_run`。
- **P2-3c:** 将 runTargetId/attemptId 自动带入 TaskGraph 生命周期，完成自动 timeline publish。
- **P2-3d:** UI 异构创建、sequence/behavior 展示与航点时间线可视化。
- **支柱四:** 航点内动作级时间线、`verdict/path_action_count` 与更细 pcap 标注。
