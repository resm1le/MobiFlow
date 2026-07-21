# P2-3b CollectionIntent 异构调度编译与治理提交 Implementation Plan

> **For agentic workers:** 按任务顺序使用测试先行；每个任务只提交列出的文件，不跟踪 `MobiFlow_Agent/.venv/`，不顺带实现 P2-3c/P2-3d。

**Goal:** 在 Agent 中建立 `CollectionIntent → IntentPlanner → DispatchPlan → DispatchPlanCompiler → governed proposal` 闭环：把受限自然语言采集意图映射为显式异构分派计划，确定性解析 P2-3a 的版本化 sequence，编译成 P2-2 `create_heterogeneous_run` 的完整参数，并通过现有 `submit_execution_proposal` 进入 Platform 显式审批流程。

**Architecture:** 六层。(1) 新增严格的 collection/dispatch Pydantic 契约，selector 以互斥 union 表达。(2) 给 HTTP/MCP adapter 增只读 `list_devices` 与 `get_run_planning_catalog` 类型化能力，复用 Platform 已有 discovery/advisory 工具。(3) `IntentPlanner` 只把受限自然语言映射为 `DispatchPlan`，不生成 sequence payload、run policy 或审批决定。(4) `DispatchPlanCompiler` 用 `SequenceCatalog`、设备快照和 Platform 默认策略做确定性校验及 snake_case→camelCase 编译。(5) `CollectionDispatchService` 先准备 `ExecutionProposal(action_tool_name="create_heterogeneous_run")`，再通过现有治理适配器提交；绝不直接调用底层 side-effect 工具，绝不自动批准 confirmation。(6) 用 MCP/HTTP 契约、Noop model、fake capability 和 P2-2 fixture 做闭环回归。

**Tech Stack:** Python 3.11、pydantic v2、现有 `ModelRuntime`/`NoopModelClient`、HTTP/MCP Platform adapters、pytest。

---

## 0. 现状核实与定稿决策

### 0.1 已核实地基

- P2-3a 已提供 `SequenceCatalog.default()`、确定性 `resolve_sequence()`、两条随 wheel 打包的 `.vN` sequence，以及只读 `draft_sequence`；Agent 当前全量基线为 `531 passed`。
- Platform 已有 `list_devices` discovery 工具，结果含 `deviceId/installedProfiles/tags/registered/online/busy/status/updatedAt`。
- Platform 已有 `get_run_planning_catalog` advisory 工具，结果含 available profiles、allowed task types、默认 run config、artifact policy、priority、retry 和 queue timeout。
- Platform 已有 `create_heterogeneous_run` execution 工具，参数 schema 已要求 `name/taskType/runConfig/artifactPolicy/dispatch`，每条 dispatch 要求 `sequenceId/profilePackage/taskPayload/select`。
- `create_heterogeneous_run` 已是 `requiresApproval=true`；Platform `propose_governed_action` 会持久化 proposal、生成 confirmation，并在批准后调用真实 action。
- Agent `PlatformAdapter.submit_execution_proposal()`、`resolve_approval()`、`ExecutionProposal` 和 `GovernedActionResult` 已完整支持治理闭环。
- Agent 目前没有类型化 device inventory / planning catalog 模型，也没有公开 discovery adapter 方法。
- `require_completed_tool_result()` 当前把 falsey result 用 `or {}` 归一化；这会把合法空列表 `[]` 错变成 `{}`，必须在实现 `list_devices` 前修正。
- Platform 的 `get_run_planning_catalog` 已比单独 `list_device_pools` 更适合作为编译上下文：它包含 pool 摘要、profile 能力和 run policy 默认值。本轮不重复调用无 selector 消费方的 `list_device_pools`。

### 0.2 本计划架构决策

1. **不新增 Platform Java 代码。** P2-3b 只消费 P2-2 和既有 planning tools；若发现 Platform schema 不一致，先补跨契约测试并报告，不在 Agent 计划里暗改服务端语义。
2. **不直连 `create_heterogeneous_run`。** Agent 编译结果必须成为 `ExecutionProposal(action_tool_name="create_heterogeneous_run")`，统一走 `submit_execution_proposal`。新增直连 adapter 方法会绕开 proposal rationale/preconditions 和现有 Agent 治理模型，本计划禁止。
3. **不自动批准。** `submit_intent` 最多返回 `APPROVAL_REQUIRED` 和 confirmation ID；只有现有 `resolve_approval` 在外部明确决定后才能创建 run。
4. **使用窄能力协议。** 新增 `CollectionDispatchPlatform` Protocol，只要求 `list_devices/get_run_planning_catalog/submit_execution_proposal`。MCP/HTTP adapter 结构化实现；不强迫 simulation adapter 支持真实异构创建，也不膨胀通用 `PlatformAdapter`。
5. **Agent 保持 sequence 权威。** planner 只选 ID；compiler 从 `SequenceCatalog` 解析完整模型并生成 P2-2 payload。Platform 不查目录，模型不生成或修改 `waypoint_sequence` JSON。
6. **受限自然语言首发。** 只支持显式 sequence/behavior 与显式 `count + tags` 或 `device IDs` 条件。模糊 sequence、未指定数量、开放式“选最好设备”等输入返回 clarification，不猜测。
7. **run policy 不由模型编造。** `task_type` 来自 `CollectionIntent`（默认 `PLUGIN_RUN`）并与 Platform `allowedTaskTypes` 校验；run config、artifact policy、priority、retry、queue timeout来自 `get_run_planning_catalog.defaultRunPolicy`。
8. **稳定错误与瞬态 warning 分离。** 未知 sequence、非法 selector、未注册/不存在的点名设备、重复点名、profile 不匹配、未知 task type是编译错误；offline/busy/QUIESCED、标签容量快照不足是 warning，最终可用性仍由 Platform 在批准执行时权威校验。
9. **编译无副作用。** `plan_intent` 与 `compile_plan` 只做 discovery、模型推理和本地构造；只有显式调用 `submit_intent/submit_plan` 才写 proposal/audit。
10. **proposal ID 对同一 turn 稳定。** 使用 `collection-dispatch:{session_id}:{turn_id}`，使同一调用方 turn 的重放进入 Platform 既有 request/proposal 幂等语义；不使用随机 ID 造成重复审批。
11. **P2-3c 后置。** 本轮不会把 runTargetId/attemptId 注入 TaskGraph，也不自动发布 waypoint timeline。批准后获得的 run ID 仅作为 governed result 返回。

---

## 1. 对外契约

### 1.1 Collection intent 与 selector

```python
class CollectionIntent(StrictModel):
    raw_text: str
    task_type: str = "PLUGIN_RUN"
    labels: list[str] = Field(default_factory=list)

class ExplicitDeviceSelector(StrictModel):
    device_ids: list[str] = Field(min_length=1)

class TaggedDeviceSelector(StrictModel):
    count: int = Field(gt=0)
    required_tags: list[str] = Field(default_factory=list)
    excluded_tags: list[str] = Field(default_factory=list)

DeviceSelector = ExplicitDeviceSelector | TaggedDeviceSelector

class DispatchEntry(StrictModel):
    sequence_id: str
    select: DeviceSelector

class DispatchPlan(StrictModel):
    name: str
    description: str | None = None
    dispatch: list[DispatchEntry] = Field(min_length=1)
```

模型约束：

- `ExplicitDeviceSelector.device_ids` 内部不能重复。
- tag required/excluded 各自去重，且交集必须为空。
- union 两支都是 `StrictModel(extra="forbid")`，所以 `device_ids + count` 混用、两者都空会在 schema 边界失败。
- list 字段实例隔离；compiler 不修改 planner 返回模型。
- `sequence_id` 先执行 P2-3a `.vN` 格式校验，存在性由 compiler 查询 catalog。

### 1.2 Planner decision

为了让模型能明确要求澄清，而不是伪造空 plan：

```python
class IntentPlannerDecisionType(str, Enum):
    PLAN = "plan"
    CLARIFY = "clarify"

class IntentPlannerDecision(StrictModel):
    decision_type: IntentPlannerDecisionType
    plan: DispatchPlan | None = None
    clarification_questions: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
```

不变量：`PLAN` 必须有 plan 且 questions 为空；`CLARIFY` 必须无 plan 且至少一个 question。

Agent service 返回：

```python
class IntentPlanningResult(StrictModel):
    status: CollectionDispatchStatus
    plan: DispatchPlan | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    issues: list[str] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)
    trace_refs: list[str] = Field(default_factory=list)
```

### 1.3 Platform discovery 类型

在 `platform/types.py` 增加最小但完整的编译视图：

```python
class DispatchDeviceContext(StrictModel):
    device_id: str
    installed_profiles: list[str]
    tags: list[str]
    host_group: str | None = None
    registered: bool
    online: bool
    busy: bool
    status: str
    updated_at: int

class PlatformRunConfig(StrictModel):
    loop_count: int
    budget_ms: int
    loop_interval_ms: int
    network_isolation_enabled: bool
    poll_interval_ms: int
    heartbeat_interval_ms: int

class PlatformArtifactPolicy(StrictModel):
    upload_log: bool
    upload_screenshot: bool
    upload_dump: bool

class RunPlanningDefaultPolicy(StrictModel):
    priority: int
    max_retries_per_device: int
    queue_timeout_ms: int
    default_run_config: PlatformRunConfig
    default_artifact_policy: PlatformArtifactPolicy

class RunPlanningCatalogContext(StrictModel):
    available_device_pools: list[...]
    available_profiles: list[...]
    default_run_policy: RunPlanningDefaultPolicy
    allowed_task_types: list[str]
```

mapping 层显式完成 camelCase→snake_case；不要给 Pydantic 模型开启全局 alias/`populate_by_name`，避免影响已有 canonical contracts。

### 1.4 编译结果与生命周期

```python
class CollectionDispatchStatus(str, Enum):
    NEEDS_CLARIFICATION = "needs_clarification"
    REJECTED = "rejected"
    ERROR = "error"
    PLANNED = "planned"
    APPROVAL_REQUIRED = "approval_required"
    EXECUTED = "executed"
    FAILED = "failed"

class DispatchCompilationResult(StrictModel):
    accepted: bool
    proposal: ExecutionProposal | None = None
    issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

class CollectionDispatchResult(StrictModel):
    status: CollectionDispatchStatus
    plan: DispatchPlan | None = None
    proposal: ExecutionProposal | None = None
    governed_result: GovernedActionResult | None = None
    issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)
    trace_refs: list[str] = Field(default_factory=list)
```

不变量：

- `PLANNED` 必须有 plan + proposal，无 governed result。
- `APPROVAL_REQUIRED/EXECUTED/FAILED` 必须有 plan + proposal + governed result，且 status 与 `GovernedActionState` 一致。
- `NEEDS_CLARIFICATION/REJECTED/ERROR` 不能携带 proposal/governed result；`ERROR` 专用于 Platform discovery/transport 等基础设施失败，不能冒充 governed action失败。模型无法形成合法 plan 仍按 `NEEDS_CLARIFICATION` 处理。

### 1.5 编译后的 proposal

```json
{
  "proposal_id": "collection-dispatch:session-1:turn-1",
  "action_tool_name": "create_heterogeneous_run",
  "arguments": {
    "name": "wechat mixed collection",
    "description": "3 text chats and 2 video calls",
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
    "source": "mobiflow-agent",
    "createdBy": "mobiflow-agent",
    "maxRetriesPerDevice": 0,
    "queueTimeoutMs": 300000,
    "dispatch": [
      {
        "sequenceId": "wechat.text_chat.v1",
        "profilePackage": "com.tencent.mm",
        "taskPayload": {
          "goal": "Run waypoint sequence wechat.text_chat.v1 for behavior wechat_text_chat.",
          "waypoint_sequence": "<full WaypointSequence model_dump(mode=json)>"
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
          "goal": "Run waypoint sequence wechat.video_call.v1 for behavior wechat_video_call.",
          "waypoint_sequence": "<full WaypointSequence model_dump(mode=json)>"
        },
        "select": {"deviceIds": ["dev-7", "dev-9"]}
      }
    ]
  },
  "preconditions": {
    "sequenceIds": ["wechat.text_chat.v1", "wechat.video_call.v1"],
    "deviceInventoryUpdatedAt": 1721550000000
  }
}
```

`taskPayload.waypoint_sequence` 实际为 JSON object，上例字符串仅表示完整嵌套对象。compiler 必须用 `model_dump(mode="json")`，不能手工挑字段。

---

## 2. 实施任务

### Task 1：定义 collection/dispatch 严格契约

**Files:**

- Create: `MobiFlow_Agent/mobiflow_agent/collection/__init__.py`
- Create: `MobiFlow_Agent/mobiflow_agent/collection/models.py`
- Create: `MobiFlow_Agent/tests/collection/test_dispatch_models.py`

- [ ] **Step 1：先写 schema 与不变量测试**

覆盖：

1. `CollectionIntent` 拒绝空白 raw text/task type，labels 实例隔离。
2. explicit selector 拒绝空列表、空白 ID、内部重复 ID。
3. tag selector 拒绝 `count<=0`、重复 tag、required/excluded 交集。
4. `DispatchEntry.select` 拒绝两种模式混用或都空。
5. `DispatchPlan.dispatch` 非空，name 非空白。
6. `IntentPlannerDecision` 的 PLAN/CLARIFY 不变量。
7. compilation/result 状态与 proposal/governed result 不变量。
8. selector、plan、result 的可变列表在实例间隔离。

- [ ] **Step 2：运行失败测试**

```bash
cd MobiFlow_Agent
pytest tests/collection/test_dispatch_models.py -q
```

Expected: FAIL，collection package 尚不存在。

- [ ] **Step 3：实现模型**

要求：

- 复用 `StrictModel`、`ExecutionProposal`、`GovernedActionResult` 和 P2-3a `SEQUENCE_ID_PATTERN`。
- selector 使用 Pydantic union，不添加 `mode` 字段，不改变 P2-2 对外 shape。
- whitespace、重复项和状态组合用 field/model validators 明确拒绝。
- `collection.__init__` 只导出 contract；如引入后续 service 造成 cycle，采用现有 lazy `__getattr__` 模式。

- [ ] **Step 4：运行测试**

```bash
cd MobiFlow_Agent
pytest tests/collection/test_dispatch_models.py tests/common/test_contracts.py -q
```

Expected: PASS。

- [ ] **Step 5：提交**

```bash
git add MobiFlow_Agent/mobiflow_agent/collection \
  MobiFlow_Agent/tests/collection/test_dispatch_models.py
git commit -m "feat(agent): define collection dispatch contracts"
```

---

### Task 2：增加类型化 Platform discovery/planning capability

**Files:**

- Modify: `MobiFlow_Agent/mobiflow_agent/platform/types.py`
- Modify: `MobiFlow_Agent/mobiflow_agent/platform/adapter/mapping.py`
- Modify: `MobiFlow_Agent/mobiflow_agent/platform/adapter/mcp.py`
- Modify: `MobiFlow_Agent/mobiflow_agent/platform/adapter/http.py`
- Create: `MobiFlow_Agent/mobiflow_agent/collection/protocol.py`
- Modify: `MobiFlow_Agent/tests/platform/test_platform_adapter.py`
- Create: `MobiFlow_Agent/tests/collection/test_dispatch_platform_protocol.py`

- [ ] **Step 1：先写 MCP/HTTP 映射失败测试**

用现有 stub transports 覆盖：

- `list_devices()` 把 camelCase 列表映射为 `DispatchDeviceContext`。
- 合法空列表保持 `[]`，不能变成 `{}` 或 contract error。
- `get_run_planning_catalog()` 完整映射 default run config/artifact policy、profiles 和 allowed task types。
- 缺必填字段、错误 result 类型、failed tool response 都抛 `PlatformAdapterError(INVALID_PLATFORM_CONTRACT 或服务端错误码)`。
- MCP 与 HTTP 得到等价 typed result。

- [ ] **Step 2：修正 falsey result helper**

将 `require_completed_tool_result()` 改为保留合法 falsey payload：仅当 `result is None` 时回 `{}`，不能使用 `response.get("result") or {}`。如返回类型不再总是 dict，重命名/新增 `require_completed_tool_payload() -> Any`，保留原 helper 给 dict 调用方并增加类型检查。

推荐：

```python
def require_completed_tool_payload(tool: str, response: dict[str, Any]) -> Any: ...
def require_completed_tool_result(tool: str, response: dict[str, Any]) -> dict[str, Any]: ...
```

list 工具使用 payload helper；现有 dict 工具继续使用 result helper，避免把宽类型传播全仓。

- [ ] **Step 3：实现 typed models/mapping**

- `map_dispatch_device_context()` 只取编译需要字段，但严格要求 Platform schema 的必填 identity/state。
- `map_run_planning_catalog_context()` 把完整默认策略转换为严格嵌套模型。
- mapping 必须复制 list/dict，调用方 mutation 不污染 adapter response fixture。

- [ ] **Step 4：实现 HTTP/MCP 公开只读方法**

```python
def list_devices(self) -> list[DispatchDeviceContext]: ...
def get_run_planning_catalog(self) -> RunPlanningCatalogContext: ...
```

- MCP 调 `_call_tool("list_devices", {})` / `_call_tool("get_run_planning_catalog", {})`。
- HTTP 调 `_execute_tool(...)` 对应工具。
- 两者都只读，不要求 caller context/approval。

- [ ] **Step 5：定义窄 Protocol 并做结构测试**

```python
class CollectionDispatchPlatform(Protocol):
    def list_devices(...) -> list[DispatchDeviceContext]: ...
    def get_run_planning_catalog(...) -> RunPlanningCatalogContext: ...
    def submit_execution_proposal(...) -> GovernedActionResult: ...
```

测试 MCP/HTTP adapter 可作为该 capability 使用；service 单测使用独立 fake，不改 `PlatformAdapter`。

- [ ] **Step 6：运行回归**

```bash
cd MobiFlow_Agent
pytest tests/platform/test_platform_adapter.py \
  tests/collection/test_dispatch_platform_protocol.py -q
```

Expected: PASS，既有 adapter 测试无回归。

- [ ] **Step 7：提交**

```bash
git add MobiFlow_Agent/mobiflow_agent/platform/types.py \
  MobiFlow_Agent/mobiflow_agent/platform/adapter/mapping.py \
  MobiFlow_Agent/mobiflow_agent/platform/adapter/mcp.py \
  MobiFlow_Agent/mobiflow_agent/platform/adapter/http.py \
  MobiFlow_Agent/mobiflow_agent/collection/protocol.py \
  MobiFlow_Agent/tests/platform/test_platform_adapter.py \
  MobiFlow_Agent/tests/collection/test_dispatch_platform_protocol.py
git commit -m "feat(agent): expose dispatch planning inventory"
```

---

### Task 3：实现受限自然语言 `IntentPlanner`

**Files:**

- Create: `MobiFlow_Agent/mobiflow_agent/collection/prompting.py`
- Create: `MobiFlow_Agent/mobiflow_agent/collection/planner.py`
- Modify: `MobiFlow_Agent/mobiflow_agent/collection/__init__.py`
- Create: `MobiFlow_Agent/tests/collection/test_intent_planner.py`

- [ ] **Step 1：先写 prompt contract 测试**

prompt context 必须包含：

- 原始 `CollectionIntent.raw_text`；
- `SequenceCatalog.list_sequences()` 摘要（ID/behavior/profile/waypoint IDs）；
- device inventory（ID/tags/installed profiles/availability）；
- Platform allowed task types/profile 摘要；
- 明确 selector 二选一规则。

system prompt 必须明确：

- 只能选择 catalog 中完整 `.vN` ID；
- 只能选择 inventory 中设备 ID 和已观察 tag；
- 不输出 sequence payload、run config、artifact policy、审批决定或 device identity 之外的字段；
- 缺 sequence/数量/设备条件或语义歧义时返回 `CLARIFY`；
- 不把 `draft_sequence` 自动串进调度，不为用户创建新 sequence。

- [ ] **Step 2：先写 planner 行为测试**

使用 `NoopModelClient`：

1. 明确“3×text_chat on android13 + dev-7/dev-9 video_call”生成 `PLANNED` result。
2. CLARIFY decision 原样保留问题，无 plan。
3. 无 model runtime/模型错误/schema 错误返回 `NEEDS_CLARIFICATION`。
4. trace refs 和 confidence 保留。
5. 模型输出 catalog 外 ID即使 schema 合法，也先由 planner result保留，最终由 compiler 拒绝；planner 不重复 catalog 存在性逻辑。

- [ ] **Step 3：运行失败测试**

```bash
cd MobiFlow_Agent
pytest tests/collection/test_intent_planner.py -q
```

Expected: FAIL，planner/prompting 尚不存在。

- [ ] **Step 4：实现 planner**

- 使用 `AgentRole.PLANNER`，支持 profile override。
- `plan()` 只做 prompt + structured generation + decision normalization。
- 捕获模型/validation error，返回 typed clarification，不抛裸异常。
- 不调用 Platform、不 resolve sequence、不构造 payload、不提交 proposal。

- [ ] **Step 5：运行测试**

```bash
cd MobiFlow_Agent
pytest tests/collection/test_intent_planner.py tests/model/test_model_runtime.py -q
```

Expected: PASS。

- [ ] **Step 6：提交**

```bash
git add MobiFlow_Agent/mobiflow_agent/collection/prompting.py \
  MobiFlow_Agent/mobiflow_agent/collection/planner.py \
  MobiFlow_Agent/mobiflow_agent/collection/__init__.py \
  MobiFlow_Agent/tests/collection/test_intent_planner.py
git commit -m "feat(agent): plan heterogeneous collection intents"
```

---

### Task 4：实现确定性 `DispatchPlanCompiler`

**Files:**

- Create: `MobiFlow_Agent/mobiflow_agent/collection/compiler.py`
- Modify: `MobiFlow_Agent/mobiflow_agent/collection/__init__.py`
- Create: `MobiFlow_Agent/tests/collection/test_dispatch_compiler.py`

- [ ] **Step 1：先写 payload 精确编译测试**

固定两条 P2-3a sequence、Platform policy 和 device inventory，断言：

- `DispatchPlan` 原顺序保持；每条 entry 的 sequence/profile/payload 对齐。
- `taskPayload.goal` 非空，`waypoint_sequence` 等于 resolve 后 `model_dump(mode="json")`。
- explicit selector 输出仅 `deviceIds`；tag selector 输出仅 `count/requiredTags/excludedTags`。
- run config/artifact policy 逐字段转成 P2-2 camelCase。
- intent labels 被复制，source/createdBy 固定 `mobiflow-agent`。
- proposal action 为 `create_heterogeneous_run`，同一 caller turn proposal ID稳定。
- compiler 不修改 plan、catalog 结果、inventory 或 policy 输入。

- [ ] **Step 2：先写稳定错误测试**

编译期拒绝且 proposal 为 None：

- sequence 不存在或无版本 ID；
- task type 不在 Platform allowlist；
- sequence profile 不在 Platform available profiles；
- 点名设备不存在或 `registered=false`；
- 同一 selector/跨 dispatch 重复点名；
- 点名设备未安装 sequence profile；
- Platform policy 缺必填 run/artifact 字段（应在 mapping 更早失败，compiler fixture 也覆盖防御）。

issues 使用稳定、可断言格式，例如：

```text
unknown_sequence:wechat.unknown.v1
unsupported_task_type:UNKNOWN
profile_unavailable:wechat.video_call.v1:com.tencent.mm
device_not_registered:dev-9
duplicate_named_device:dev-7
device_profile_missing:dev-7:com.tencent.mm
```

- [ ] **Step 3：先写瞬态 warning 测试**

不阻断 proposal：

- 点名设备 offline/busy/QUIESCED；
- tag snapshot 当前可用容量小于 count；
- required tag 当前未在任何设备出现。

warning 必须说明“Platform 在批准执行时重新权威校验”，不得把当前 snapshot 当 reservation。

- [ ] **Step 4：运行失败测试**

```bash
cd MobiFlow_Agent
pytest tests/collection/test_dispatch_compiler.py -q
```

Expected: FAIL，compiler 尚不存在。

- [ ] **Step 5：实现 deterministic compiler**

输入：

```python
compile(
    intent,
    plan,
    *,
    sequence_catalog,
    devices,
    planning_catalog,
    caller_context,
    planning_confidence,
) -> DispatchCompilationResult
```

实现顺序：

1. 校验 task type/profile/catalog/device identity 等稳定条件，聚合全部 issues。
2. 计算 snapshot warnings，但不复制 Platform reservation/claim 逻辑。
3. 所有 issues 为空后 resolve 每条 sequence 的深拷贝并构造 entry payload。
4. 使用 Platform default policy 构造 arguments。
5. 构造 `ExecutionProposal`；`confidence=planning_confidence`，direct structured plan调用可显式传 `1.0`。

- [ ] **Step 6：做 P2-2 跨契约测试**

复用 `p2-2-resolved-sequence.json` 或现有 Platform fixture，验证 compiler 产出的 `wechat.text_chat.v1` envelope 在 identity/profile/waypoint IDs 上与 Platform contract 一致。不要从 Platform fixture加载生产 sequence。

- [ ] **Step 7：运行测试**

```bash
cd MobiFlow_Agent
pytest tests/collection/test_dispatch_compiler.py \
  tests/waypoint/test_platform_sequence_contract.py -q
```

Expected: PASS。

- [ ] **Step 8：提交**

```bash
git add MobiFlow_Agent/mobiflow_agent/collection/compiler.py \
  MobiFlow_Agent/mobiflow_agent/collection/__init__.py \
  MobiFlow_Agent/tests/collection/test_dispatch_compiler.py \
  MobiFlow_Agent/tests/waypoint/test_platform_sequence_contract.py
git commit -m "feat(agent): compile heterogeneous dispatch proposals"
```

若跨契约测试无需修改，不把它加入 `git add`。

---

### Task 5：实现 `CollectionDispatchService` 治理闭环

**Files:**

- Create: `MobiFlow_Agent/mobiflow_agent/collection/service.py`
- Modify: `MobiFlow_Agent/mobiflow_agent/collection/__init__.py`
- Create: `MobiFlow_Agent/tests/collection/test_collection_dispatch_service.py`

- [ ] **Step 1：先写 prepare-only 测试**

`plan_intent(intent, caller_context)`：

- 依次获取 devices、planning catalog、sequence summaries；
- 调 IntentPlanner，再调用 compiler；
- planner `PLANNED` + compiler accepted 返回 service `PLANNED`、plan、proposal、warnings、trace refs；
- clarification/rejected 返回对应状态且不调用 `submit_execution_proposal`；
- discovery adapter error 返回 `ERROR`，不产生 proposal；retryable 属性保留在 issue/warning 约定中。

- [ ] **Step 2：先写 submit 测试**

`submit_intent(intent, caller_context)`：

- 先复用 prepare 流程，再唯一一次调用 `submit_execution_proposal`。
- governed `APPROVAL_REQUIRED` 映射为 collection `APPROVAL_REQUIRED`，保留 confirmation/audit/entity refs。
- governed `EXECUTED` 映射为 `EXECUTED` 并保留 run ID（适用于 Platform policy未来允许即时执行或 replay 已批准结果）。
- governed `FAILED` 映射为 `FAILED`，保留 typed error。
- 不调用 `resolve_approval`，不自动批准。

- [ ] **Step 3：先写 direct structured plan 测试**

`submit_plan(intent, plan, caller_context)` 跳过 model planner但仍执行 discovery、compiler、governed proposal；这为 UI/API 和确定性测试提供入口。它不能绕过 compile validation 或 approval。

- [ ] **Step 4：运行失败测试**

```bash
cd MobiFlow_Agent
pytest tests/collection/test_collection_dispatch_service.py -q
```

Expected: FAIL，service 尚不存在。

- [ ] **Step 5：实现 service**

依赖注入：

```python
CollectionDispatchService(
    platform: CollectionDispatchPlatform,
    sequence_catalog: SequenceCatalog,
    intent_planner: IntentPlanner,
    compiler: DispatchPlanCompiler,
)
```

- discovery 每次调用重新获取，不能缓存跨 turn 的 busy/online snapshot。
- direct plan 与 model plan共用同一 compiler。
- trace refs 做保持首次顺序的去重。
- PlatformAdapterError 转为稳定 issue，不能吞 retryable 信息。
- service 不持有 confirmation decision，不创建 TaskGraph session。

- [ ] **Step 6：运行治理回归**

```bash
cd MobiFlow_Agent
pytest tests/collection/test_collection_dispatch_service.py \
  tests/platform/test_platform_adapter.py \
  tests/runtime/test_runtime_state.py -q
```

Expected: PASS，既有 confirmation/runtime contract 无回归。

- [ ] **Step 7：提交**

```bash
git add MobiFlow_Agent/mobiflow_agent/collection/service.py \
  MobiFlow_Agent/mobiflow_agent/collection/__init__.py \
  MobiFlow_Agent/tests/collection/test_collection_dispatch_service.py
git commit -m "feat(agent): submit governed collection dispatches"
```

---

### Task 6：文档、范围检查与总回归

**Files:**

- Modify: `MobiFlow_Agent/README.md`
- Modify: `AI_Mobile_Executor_Platform/docs/protocol.md`
- Modify: `docs/superpowers/specs/2026-07-20-pillar2-waypoint-scheduling-design.md`

- [ ] **Step 1：更新 Agent 使用文档**

展示两个入口：

```python
prepared = service.plan_intent(intent, caller_context)
submitted = service.submit_intent(intent, caller_context)
```

明确 `submitted.status == APPROVAL_REQUIRED` 不是失败，也不是已创建 run；调用方必须展示 confirmation 并通过既有 `resolve_approval` 接受用户决定。

- [ ] **Step 2：更新协议与总体设计**

记录：

- P2-3b 复用 `list_devices + get_run_planning_catalog`；
- Agent resolve sequence 并构造完整 payload；
- `create_heterogeneous_run` 通过 `propose_governed_action` 提交；
- direct `create_heterogeneous_run` adapter不是 Agent 标准入口；
- compiler snapshot 不构成设备 reservation，Platform批准执行时仍权威校验。

- [ ] **Step 3：运行 collection targeted tests**

```bash
cd MobiFlow_Agent
pytest tests/collection tests/waypoint tests/platform/test_platform_adapter.py -q
```

Expected: PASS，无新增 skip。

- [ ] **Step 4：运行 Agent 全量**

```bash
cd MobiFlow_Agent
pytest -q
```

Expected: 全部通过，无 P2-3b 新增 skip。

- [ ] **Step 5：范围检查**

```bash
git status --short
git diff --check
git diff --stat
rg -n "record_waypoint_segments|run_target_id|attempt_id|resolve_approval" \
  MobiFlow_Agent/mobiflow_agent/collection
```

Expected:

- collection 代码不含 P2-3c lineage/timeline publish；
- `resolve_approval` 只能出现在文档/负向测试断言，不由 service调用；
- 没有 Platform Java、DB migration 或 Console 源码改动；
- `.venv/` 未跟踪；`git diff --check` 无输出。

- [ ] **Step 6：提交**

```bash
git add MobiFlow_Agent/README.md \
  AI_Mobile_Executor_Platform/docs/protocol.md \
  docs/superpowers/specs/2026-07-20-pillar2-waypoint-scheduling-design.md
git commit -m "docs: document governed collection dispatch"
```

---

## 3. 验收矩阵

| 能力 | 正向验收 | 失败/边界验收 |
|---|---|---|
| selector schema | explicit IDs 或 count+tags | 混用、都空、重复、交叉 tags 拒绝 |
| inventory discovery | HTTP/MCP 映射等价 typed contexts | 空列表保真、坏 result/字段拒绝 |
| planning policy | 使用 Platform 默认 run/artifact policy | 未知 task type/profile 编译拒绝 |
| NL planner | 显式 X/Y + 设备条件生成 plan | 模糊/缺条件返回 clarification |
| sequence resolve | `.vN` ID解析完整 Pydantic模型 | 未知/非法 ID 不产生 proposal |
| device identity | 注册且 profile匹配的点名设备通过 | 不存在/未注册/profile缺失拒绝 |
| transient state | offline/busy/容量不足形成 warning | 不把 snapshot冒充 reservation |
| payload compile | snake→camel 与完整 sequence envelope | plan/catalog/inventory 输入不被修改 |
| governance | proposal 进入 approval required | 无 direct action、无自动 approve |
| replay | 同 caller turn proposal ID稳定 | 不因随机 ID生成重复审批 |
| direct plan | 跳过模型但复用 compiler/governance | 不能绕过 validation/approval |
| scope | Agent collection 层闭环 | 无 Java/DB/UI/P2-3c 改动 |

---

## 4. Definition of Done

- `CollectionIntent`、`DispatchPlan`、两种互斥 selector 和 lifecycle result均为严格 Pydantic contract。
- `IntentPlanner` 对明确受限自然语言生成异构 plan，对模糊输入返回结构化 clarification。
- HTTP/MCP adapter 能类型化读取空/非空 device inventory 和完整 Platform planning catalog。
- `require_completed_tool_result` 不再损坏合法 falsey payload，既有 dict调用无回归。
- compiler 解析 P2-3a 正式 sequence，生成 P2-2 接受的完整 per-entry task payload。
- compiler 在 proposal 前拒绝未知 sequence、非法 selector、未注册/重复设备、profile/task type不匹配。
- transient device状态与容量只形成 warning，文档明确 snapshot不是 reservation。
- run config/artifact policy/priority/retry/timeout来自 Platform planning catalog，不由模型编造。
- proposal 固定指向 `create_heterogeneous_run`，同 caller turn ID稳定，并携带 rationale/preconditions/confidence。
- `CollectionDispatchService` 同时提供 model intent和 direct structured plan入口；两者共用 compiler。
- 所有 side effect通过 `submit_execution_proposal`；service 不直连 create、不自动调用 `resolve_approval`。
- approval required、executed、failed均正确映射并保留 audit/entity refs/error。
- collection/waypoint/platform targeted tests与 Agent全量测试通过，无新增 skip。
- 文档与代码一致，工作区仅保留用户未跟踪 `.venv/`。

---

## 5. 明确后置

- **P2-2 发布验证门：** Docker环境实际执行 V10/V11、MySQL唯一键、锁与 pinned claim，仍不可用 Agent单测替代。
- **跨 run reservation：** P2-3b snapshot与 Platform claim不提供创建期全局设备预留；产品若要求批次独占，另立 Platform计划。
- **P2-3c：** `WaypointEvidencePublisher` capability、runTargetId/attemptId execution lineage、terminal attempt自动 timeline publish。
- **P2-3d：** sequence/behavior/timeline展示、异构创建 UI、confirmation交互、AI草稿人工入库。
- **复杂 NL：** “选择最合适设备”“自动组合行为”“按容量优化”等多目标规划后置；首版不猜测。
- **支柱三/四：** rendezvous跨设备 barrier、航点内动作级 timeline、`verdict/path_action_count`、更细 pcap标注。
