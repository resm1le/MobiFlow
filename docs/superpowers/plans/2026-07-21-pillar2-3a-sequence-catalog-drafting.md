# P2-3a Agent 序列目录与 AI 草稿 Implementation Plan

> **For agentic workers:** 按任务顺序执行，使用测试先行；每个任务完成后只提交该任务列出的文件，不夹带 `MobiFlow_Agent/.venv/` 或其他用户改动。

**Goal:** 在 Agent 内建立版本化、确定性、只读的 `WaypointSequence` 目录，提供 `resolve_sequence` 编程接口；同时提供复用现有 intake/model runtime 的 `draft_sequence` 分析接口，把自然语言或遗留脚本文本转换为可人工评审的航点序列草稿，但绝不自动写入正式目录。

**Architecture:** 分两条严格隔离的路径。(1) `SequenceCatalog` 从 Agent 随包 JSON 资源构建一次性只读快照，加载时用现有 Pydantic `WaypointSequence` 做全量校验，按版本化 `sequence_id` 确定性查询，并对外返回深拷贝。(2) `SequenceDraftService` 先用现有 `TestCaseParser` 获取结构化用例，再由只读 `WaypointDraftDecomposer` 把全局用例分解成逐航点到达结果，最后逐航点复用 `AssertionSynthesizer` 生成可观察的 `VerificationSpec`。草稿结果只存在于返回值；正式入库仍是人工编辑 JSON、代码评审和 catalog 测试通过后的显式动作。Platform 继续只接收已解析 payload，不复制 Agent schema 或目录。

**Tech Stack:** Python 3.11、pydantic v2、`importlib.resources`、现有 `ModelRuntime`/`NoopModelClient`、pytest。

---

## 0. 现状核实与定稿决策

### 0.1 已有地基

- `mobiflow_agent.waypoint.models.WaypointSequence` 已定义 `sequence_id`、`behavior_label`、`profile_package` 和非空、航点 ID 唯一约束。
- `compile_sequence_to_plan` 与 `TaskGraphRuntime.create_session(..., waypoint_sequence=...)` 已能直接消费解析后的模型。
- P2-2 的 `create_heterogeneous_run` 已接收 `sequenceId + profilePackage + taskPayload`，并校验三者一致；Platform 不负责查目录。
- `TaskIntakeService` 已有 `TestCaseParser → TestCaseValidator → AssertionSynthesizer → TestCaseAssembler` 流程。
- `TestCase.expected_outcomes` 是整个用例的全局结果；`TestCaseAssembler` 只会把全部 checks 聚合成一个 `VerificationSpec`，不能可靠地产生多个航点的逐点 `arrival_spec`。
- `AssertionSynthesizer` 已限定可用 fact catalog 和谓词操作符，并在模型产出非法 fact 时重试一次。
- 当前 setuptools 配置未声明 JSON package data；直接新增目录文件会在 wheel 安装后丢失。

### 0.2 本计划的架构决策

1. **Agent 是序列定义的唯一权威。** 较新的 P2-2 协议已经明确 `resolve_sequence`/`draft_sequence` 在 Platform 协议之外；总体设计中“给 Java `ToolFacadeService` 增加这两个工具”的旧描述由本计划纠正。
2. **P2-3a 只提供 Agent 编程接口。** 当前 Agent 没有独立 tool server/facade；不为了两个方法新建 MCP 层。P2-3b 的 `IntentPlanner` 直接依赖这些服务。
3. **目录是随包 JSON 资源，不是数据库。** 不加写 API、热更新、latest alias、复杂版本表或远程存储。`sequence_id` 显式带 `.vN`。
4. **目录加载是原子的。** 任一文件 JSON 非法、模型非法、ID 未版本化或 ID 重复，整个快照构建失败，不允许部分目录继续服务。
5. **查询结果隔离可变状态。** `resolve_sequence` 每次返回 `model_copy(deep=True)`；调用方修改 `waypoints`/`allowed_actions` 不会污染目录或其他调用。
6. **AI 不能决定稳定身份。** `sequence_id`、`behavior_label`、`profile_package` 由调用方在 `SequenceDraftRequest` 中明确提供，模型只能分解航点、到达结果和显式路径约束。
7. **不直接复用 `TestCaseAssembler`。** 新增航点分解阶段，为每个航点提供一个或多个自然语言 `arrival_outcomes`；然后逐航点调用现有 `AssertionSynthesizer`，为该航点单独构建 `VerificationSpec`。
8. **草稿是原子结果。** 任一航点无法获得至少一个合法 check、出现重复 waypoint ID、越权 action 或模型错误时，不返回“半条可执行 sequence”；返回结构化问题和澄清问题。
9. **只读草稿不触发执行审批。** 不复用 `TestCaseValidator` 中的 `confirmation_required` 执行门禁；草稿服务只做结构、安全白名单和可观察性校验。风险信息可作为 warning 保留，真正创建 run 仍由 P2-3b/P2-2 显式审批。
10. **不顺带实现 P2-3b/P2-3c。** 本计划不增加 `CollectionIntent`、selector、设备查询、`create_heterogeneous_run` adapter、runTargetId/attemptId 生命周期或自动时间线上报。

### 0.3 `sequence_id` 规则

目录和草稿入口采用：

```text
^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*\.v[1-9][0-9]*$
```

合法示例：`capture.v1`、`wechat.text_chat.v1`、`shopping.checkout.v2`。

不在本轮支持：`latest`、`v0`、大小写 ID、无版本 ID、版本范围或自动升级。

---

## 1. 对外契约

### 1.1 `SequenceCatalog`

```python
class SequenceCatalog:
    @classmethod
    def from_directory(cls, directory: Path) -> "SequenceCatalog": ...

    @classmethod
    def default(cls) -> "SequenceCatalog": ...

    def list_sequences(self) -> list[SequenceSummary]: ...

    def resolve_sequence(self, sequence_id: str) -> WaypointSequence: ...
```

要求：

- `default()` 用 `importlib.resources` 读取 `mobiflow_agent/waypoint/sequences/*.json`；不得依赖当前工作目录。
- `from_directory()` 仅用于显式自定义目录和测试，按文件名排序后加载，保证错误顺序稳定。
- `list_sequences()` 按 `sequence_id` 排序，返回轻量摘要，不暴露目录内部模型实例。
- `resolve_sequence()` 只接受完整版本 ID；不存在时抛出带 `code/message/sequence_id` 的 `SequenceCatalogError`。
- 不提供 `add`、`save`、`delete`、`resolve_latest` 或隐式 reload。

建议模型：

```python
class SequenceSummary(StrictModel):
    sequence_id: str
    behavior_label: str
    profile_package: str
    waypoint_ids: list[str]

class SequenceCatalogError(RuntimeError):
    code: str
    message: str
    sequence_id: str | None
    source: str | None
```

错误码至少覆盖：

- `SEQUENCE_CATALOG_NOT_FOUND`
- `SEQUENCE_SOURCE_INVALID_JSON`
- `SEQUENCE_DEFINITION_INVALID`
- `SEQUENCE_ID_INVALID`
- `SEQUENCE_ID_DUPLICATE`
- `SEQUENCE_NOT_FOUND`

### 1.2 `draft_sequence`

```python
class SequenceDraftSourceKind(str, Enum):
    NATURAL_LANGUAGE = "natural_language"
    LEGACY_SCRIPT = "legacy_script"

class SequenceDraftRequest(StrictModel):
    source_text: str
    source_kind: SequenceDraftSourceKind = SequenceDraftSourceKind.NATURAL_LANGUAGE
    sequence_id: str
    behavior_label: str
    profile_package: str

class SequenceDraftResult(StrictModel):
    status: TaskIntakeStatus
    sequence: WaypointSequence | None = None
    issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)
    trace_refs: list[str] = Field(default_factory=list)
```

候选模型只承载模型可以辅助判断的内容：

```python
class DraftWaypointCandidate(StrictModel):
    waypoint_id: str
    description: str
    arrival_outcomes: list[ExpectedOutcome]
    strength: WaypointStrength = WaypointStrength.COMMONSENSE
    path_constraint: PathConstraint | None = None
    allowed_actions: list[str] = Field(default_factory=lambda: list(DEFAULT_MOBILE_ACTIONS))

class SequenceWaypointDraftCandidate(StrictModel):
    waypoints: list[DraftWaypointCandidate]
```

模型候选不得包含或覆盖 `sequence_id`、`behavior_label`、`profile_package`，也不生成 `rendezvous`。

服务流程：

```text
SequenceDraftRequest
  → TestCaseParser.parse(source_text)
  → draft-specific structural/safety validation
  → WaypointDraftDecomposer.decompose(TestCase, request metadata)
  → validate waypoint ids/actions/outcomes/path constraints
  → AssertionSynthesizer.synthesize(one waypoint's outcomes) × N
  → VerificationSpec per waypoint
  → WaypointSequence supplied identity + generated waypoints
  → SequenceDraftResult(READY)
```

状态语义：

- `READY`：完整 sequence 已通过 Pydantic、白名单和逐航点 assertion 校验。
- `NEEDS_CLARIFICATION`：缺模型运行时、parser/decomposer/synthesizer 失败、到达结果不可观察或输入语义不足。
- `REJECTED`：模型产出越权 action、重复 waypoint ID 或其他明确违反安全/结构契约的内容。
- 非 `READY` 时 `sequence` 必须为 `None`。

### 1.3 提示词约束

`WaypointDraftPromptBuilder` 必须要求模型：

- 只把来源文本拆成语义航点，不输出点击坐标或设备身份；
- 每个航点至少给出一个“到达后可观察”的 outcome，而不是把动作本身当成到达证明；
- 不发明来源中不存在的账号、联系人、商品、设备或 App package；
- `allowed_actions` 只能来自提供的 allowlist；
- 只有来源显式说明路径限制时才设置 `path_constraint`；
- 不生成 `rendezvous`，跨设备同步留给支柱三；
- 返回结构化 `SequenceWaypointDraftCandidate`，不返回正式 catalog 文件。

---

## 2. 实施任务

### Task 1：建立确定性 `SequenceCatalog` 契约

**Files:**

- Create: `MobiFlow_Agent/mobiflow_agent/waypoint/catalog.py`
- Modify: `MobiFlow_Agent/mobiflow_agent/waypoint/__init__.py`
- Create: `MobiFlow_Agent/tests/waypoint/test_sequence_catalog.py`

- [ ] **Step 1：先写目录行为测试**

覆盖：

1. 自定义临时目录加载合法 JSON，`list_sequences()` 按 ID 排序。
2. `resolve_sequence()` 返回完整 `WaypointSequence`。
3. 连续两次 resolve 返回不同对象；修改第一次结果的 `allowed_actions` 和 `waypoints` 不影响第二次结果。
4. 未知 ID 返回 `SEQUENCE_NOT_FOUND`，且错误包含请求 ID。
5. 非法 JSON、Pydantic 非法定义、无 `.vN` ID、重复 ID 分别返回稳定错误码。
6. 一个坏文件导致整个 `from_directory()` 失败，不能得到部分 catalog。
7. 空目录允许构建空 catalog，但 `resolve_sequence` 始终 not found；目录本身不存在则是 `SEQUENCE_CATALOG_NOT_FOUND`。

测试辅助函数用 pytest `tmp_path` 写最小合法 JSON；测试文件自身可以写 fixture，不新增生产写 API。

- [ ] **Step 2：运行失败测试**

```bash
cd MobiFlow_Agent
python -m pytest tests/waypoint/test_sequence_catalog.py -q
```

Expected: FAIL，`mobiflow_agent.waypoint.catalog` 尚不存在。

- [ ] **Step 3：实现 catalog**

实现要点：

- 路径按名称排序后逐个 `json.loads`。
- JSON 顶层必须是 object。
- 用 `WaypointSequence.model_validate` 做权威 schema 校验，不在 catalog 复制字段校验逻辑。
- 版本 ID 规则只在 catalog/draft 边界执行，不收紧底层 `WaypointSequence`，避免破坏已有内部测试里的简化 ID。
- 全部文件验证完成后才构建 `_sequences` 字典。
- `_sequences` 不对外暴露；list/resolve 都创建新对象。

- [ ] **Step 4：运行测试并检查导出**

```bash
cd MobiFlow_Agent
python -m pytest tests/waypoint/test_sequence_catalog.py tests/waypoint/test_waypoint_models.py -q
```

Expected: PASS。

- [ ] **Step 5：提交**

```bash
git add MobiFlow_Agent/mobiflow_agent/waypoint/catalog.py \
  MobiFlow_Agent/mobiflow_agent/waypoint/__init__.py \
  MobiFlow_Agent/tests/waypoint/test_sequence_catalog.py
git commit -m "feat(agent): add deterministic sequence catalog"
```

---

### Task 2：加入随包版本化序列资源

**Files:**

- Create: `MobiFlow_Agent/mobiflow_agent/waypoint/sequences/wechat.text_chat.v1.json`
- Create: `MobiFlow_Agent/mobiflow_agent/waypoint/sequences/wechat.video_call.v1.json`
- Modify: `MobiFlow_Agent/pyproject.toml`
- Modify: `MobiFlow_Agent/tests/waypoint/test_sequence_catalog.py`
- Modify: `MobiFlow_Agent/tests/waypoint/test_platform_sequence_contract.py`

- [ ] **Step 1：先写默认目录与打包测试**

断言：

- `SequenceCatalog.default()` 至少解析 `wechat.text_chat.v1` 与 `wechat.video_call.v1`。
- 两条定义都通过 `WaypointSequence` 校验、含非空航点并使用 `com.tencent.mm` profile。
- `importlib.resources.files("mobiflow_agent.waypoint").joinpath("sequences")` 能枚举 JSON。
- P2-2 contract fixture 中的 `wechat.text_chat.v1` 与 Agent catalog 的同 ID 定义在 `sequence_id/behavior_label/profile_package/waypoint_id` 上一致。

- [ ] **Step 2：运行失败测试**

```bash
cd MobiFlow_Agent
python -m pytest tests/waypoint/test_sequence_catalog.py tests/waypoint/test_platform_sequence_contract.py -q
```

Expected: FAIL，默认资源和 package-data 配置尚不存在。

- [ ] **Step 3：添加人工维护的 JSON**

要求：

- 只使用已由支柱二设计确认的 text-chat 与 video-call 示例语义。
- 每条 sequence 至少一个航点，每个航点都有合法 `arrival_spec`。
- `verification_spec.target_id == waypoint_id`。
- 不加入 `deviceId`、selector、run policy、时间线或 AI provenance。
- 不从 Platform test resources 读取生产定义；Agent 文件是唯一生产权威。

- [ ] **Step 4：声明 package data**

在 `pyproject.toml` 增加：

```toml
[tool.setuptools.package-data]
mobiflow_agent = ["waypoint/sequences/*.json"]
```

默认加载使用 `importlib.resources`，不能写死仓库绝对路径。

- [ ] **Step 5：运行 targeted + 安装包 smoke test**

```bash
cd MobiFlow_Agent
python -m pytest tests/waypoint/test_sequence_catalog.py tests/waypoint/test_platform_sequence_contract.py -q
python -c 'from mobiflow_agent.waypoint import SequenceCatalog; print([item.sequence_id for item in SequenceCatalog.default().list_sequences()])'
p2_3a_wheel_dir="$(mktemp -d)"
python -m pip wheel --no-deps --wheel-dir "$p2_3a_wheel_dir" .
python -m zipfile -l "$p2_3a_wheel_dir"/mobiflow_agent-*.whl | rg 'waypoint/sequences/.+\.json'
```

Expected: PASS，输出两个按 ID 排序的版本化序列，wheel 清单包含两份 JSON。

- [ ] **Step 6：提交**

```bash
git add MobiFlow_Agent/mobiflow_agent/waypoint/sequences \
  MobiFlow_Agent/pyproject.toml \
  MobiFlow_Agent/tests/waypoint/test_sequence_catalog.py \
  MobiFlow_Agent/tests/waypoint/test_platform_sequence_contract.py
git commit -m "feat(agent): package initial waypoint sequences"
```

---

### Task 3：定义航点草稿模型与只读分解器

**Files:**

- Create: `MobiFlow_Agent/mobiflow_agent/waypoint/drafting.py`
- Create: `MobiFlow_Agent/mobiflow_agent/waypoint/prompting.py`
- Modify: `MobiFlow_Agent/mobiflow_agent/waypoint/__init__.py`
- Create: `MobiFlow_Agent/tests/waypoint/test_sequence_drafting.py`

- [ ] **Step 1：先写 request/result/candidate 模型测试**

覆盖：

- request 拒绝空 source、空 behavior/profile 和无版本 sequence ID。
- candidate 要求非空 waypoints、每个 waypoint 非空 arrival outcomes。
- result 非 `READY` 时不能携带 sequence；`READY` 必须携带 sequence。
- 可变 list 在 request/candidate/result 实例之间隔离。

`SequenceDraftResult` 用 model validator 固化状态不变量，避免调用方收到自相矛盾的结果。

- [ ] **Step 2：先写分解器 prompt/runtime 测试**

使用现有 `NoopModelClient` 断言：

- `WaypointDraftDecomposer` 使用 `AgentRole.TASK_INTERPRETER` 和可覆盖的 profile。
- prompt context 包含解析后的 `TestCase`、`source_kind`、权威 sequence metadata 和允许动作列表。
- prompt 明确禁止设备身份、package 发明、rendezvous 和自动入库。
- 模型异常转成受控 decomposition failure，不泄漏半成品。
- 成功结果保留 model invocation trace ref。

- [ ] **Step 3：运行失败测试**

```bash
cd MobiFlow_Agent
python -m pytest tests/waypoint/test_sequence_drafting.py -q
```

Expected: FAIL，drafting/prompting 尚不存在。

- [ ] **Step 4：实现模型、prompt builder 和 decomposer**

实现时：

- 复用 `ExpectedOutcome`、`PathConstraint`、`WaypointStrength` 和公共 action tuple。
- candidate 中不出现 sequence identity 字段。
- decomposer 只负责结构化模型调用，不构造正式 `WaypointSequence`。
- 模型异常返回 typed result/exception，由 service 在 Task 4 统一转为 `NEEDS_CLARIFICATION`。

- [ ] **Step 5：运行测试**

```bash
cd MobiFlow_Agent
python -m pytest tests/waypoint/test_sequence_drafting.py tests/model/test_model_runtime.py -q
```

Expected: PASS。

- [ ] **Step 6：提交**

```bash
git add MobiFlow_Agent/mobiflow_agent/waypoint/drafting.py \
  MobiFlow_Agent/mobiflow_agent/waypoint/prompting.py \
  MobiFlow_Agent/mobiflow_agent/waypoint/__init__.py \
  MobiFlow_Agent/tests/waypoint/test_sequence_drafting.py
git commit -m "feat(agent): define waypoint sequence drafts"
```

---

### Task 4：实现 `SequenceDraftService`

**Files:**

- Modify: `MobiFlow_Agent/mobiflow_agent/waypoint/drafting.py`
- Modify: `MobiFlow_Agent/mobiflow_agent/waypoint/__init__.py`
- Modify: `MobiFlow_Agent/tests/waypoint/test_sequence_drafting.py`

- [ ] **Step 1：先写完整流水线测试**

至少覆盖：

1. `TestCaseParser → decomposer → AssertionSynthesizer × N` 生成两航点 sequence。
2. request 的 `sequence_id/behavior_label/profile_package` 原样进入最终 sequence，模型不能覆盖。
3. 每个 `VerificationSpec.target_id` 等于对应 waypoint ID；checks 只属于该 waypoint。
4. trace refs 包含 parser、decomposer 和每个 assertion synthesis invocation，顺序稳定且去重。
5. parser 无 runtime/失败时返回 `NEEDS_CLARIFICATION`。
6. decomposer 失败、空航点、空 arrival outcomes、无法合成谓词时返回 `NEEDS_CLARIFICATION` 且 `sequence=None`。
7. 重复 waypoint ID、未知 allowed action 返回 `REJECTED` 且 `sequence=None`。
8. parser 给出的执行 `risk_flags` 只形成 warning，不要求草稿审批，也不创建 session/run。
9. 显式 `path_constraint` 被保留；来源未提供时不凭空生成。
10. service 不接收 catalog 写句柄，调用完成前后 `SequenceCatalog.list_sequences()` 不变。

完整成功测试使用 `NoopModelClient` 按顺序返回：`TestCase`、`SequenceWaypointDraftCandidate`、每个航点的 `SynthesizedAssertion`。另外用注入 stub 精确测试各失败边界。

- [ ] **Step 2：运行失败测试**

```bash
cd MobiFlow_Agent
python -m pytest tests/waypoint/test_sequence_drafting.py -q
```

Expected: FAIL，`SequenceDraftService` 尚未实现。

- [ ] **Step 3：实现 draft-specific 校验**

校验分层：

- parser 负责把来源文本规范化为 `TestCase`；调用时通过 `platform_context` 带入 `source_kind`，使遗留脚本文本与自然语言目标可区分，但不把它伪装成设备上下文；
- service 检查 hint actions 白名单，但不调用执行审批门禁；
- decomposer candidate 检查非空、唯一 waypoint ID、非空 outcomes、allowed actions 子集；
- `AssertionSynthesizer` 检查 fact/operator/field path；
- service 检查同一 waypoint 内 `check_id` 唯一；
- 最后由 `WaypointSequence` 做整体模型校验。

- [ ] **Step 4：逐航点合成 arrival spec**

对每个 candidate waypoint 构造只含该 waypoint `arrival_outcomes` 的轻量 `TestCase`，调用既有 `AssertionSynthesizer.synthesize()`，然后生成：

```python
VerificationSpec(
    verification_id=f"verification:task:{waypoint_id}:arrival",
    target_kind=EntityKind.TASK,
    target_id=waypoint_id,
    success_checks=list(synthesis.checks),
)
```

不得调用 `TestCaseAssembler` 聚合全局 checks。

- [ ] **Step 5：保证原子结果与可追踪性**

- 任一步失败立即返回非 READY 结果，`sequence=None`。
- 已产生的 invocation IDs 仍进入 `trace_refs`，方便诊断。
- 对重复 trace ID 做保持首次顺序的去重。
- 不吞掉可操作 issue，例如 `waypoint:logged_in:no_valid_assertion`。

- [ ] **Step 6：运行 targeted 回归**

```bash
cd MobiFlow_Agent
python -m pytest \
  tests/waypoint/test_sequence_drafting.py \
  tests/intake/test_testcase_parser.py \
  tests/intake/test_assertion_synthesizer.py \
  tests/intake/test_testcase_validator.py -q
```

Expected: PASS。

- [ ] **Step 7：提交**

```bash
git add MobiFlow_Agent/mobiflow_agent/waypoint/drafting.py \
  MobiFlow_Agent/mobiflow_agent/waypoint/__init__.py \
  MobiFlow_Agent/tests/waypoint/test_sequence_drafting.py
git commit -m "feat(agent): draft waypoint sequences from intake"
```

---

### Task 5：补齐文档、边界契约与总回归

**Files:**

- Modify: `MobiFlow_Agent/README.md`
- Modify: `docs/superpowers/specs/2026-07-20-pillar2-waypoint-scheduling-design.md`
- Modify if needed: `MobiFlow_Agent/tests/waypoint/test_platform_sequence_contract.py`

- [ ] **Step 1：更新 Agent 使用文档**

给出最小示例：

```python
catalog = SequenceCatalog.default()
sequence = catalog.resolve_sequence("wechat.text_chat.v1")

result = draft_service.draft_sequence(
    SequenceDraftRequest(
        source_text="...",
        sequence_id="wechat.text_chat.v2",
        behavior_label="wechat_text_chat",
        profile_package="com.tencent.mm",
    )
)
```

文档明确：

- resolve 是确定性只读查询；
- draft 需要模型运行时，结果必须人工评审；
- draft 不会写 catalog；
- 创建异构 run 仍属于 P2-3b，并需要 Platform 显式确认。

- [ ] **Step 2：纠正总体设计中的旧边界**

将设计文档关键实现文件中“Platform `ToolFacadeService` 新增 `resolve_sequence`/`draft_sequence`”改为：

- Agent `SequenceCatalog`/`SequenceDraftService` 负责 resolve/draft；
- Platform `create_heterogeneous_run` 只消费已解析 payload；
- 如未来需要远程工具暴露，只允许薄代理，不复制目录和 Pydantic schema。

- [ ] **Step 3：运行 Agent 全量测试**

```bash
cd MobiFlow_Agent
python -m pytest -q
```

Expected: 全部通过；不得出现因 P2-3a 新增的 skip。

- [ ] **Step 4：运行跨模块契约 smoke tests**

```bash
cd MobiFlow_Agent
python -m pytest \
  tests/waypoint \
  tests/graph/test_waypoint_session_integration.py \
  tests/platform/test_platform_adapter.py -q
```

Expected: PASS，catalog 解析出的 sequence 仍能编译为 TaskPlan，P2-2 adapter 契约无回归。

- [ ] **Step 5：检查范围与工作区**

```bash
git status --short
git diff --check
git diff --stat
rg -n "create_heterogeneous_run|run_target_id|attempt_id|record_waypoint_segments" \
  MobiFlow_Agent/mobiflow_agent/waypoint
```

Expected:

- waypoint 新代码不包含设备调度、execution lineage 或 evidence publish；
- `.venv/` 未被跟踪；
- 没有 Java/Console 源码改动；
- `git diff --check` 无输出。

- [ ] **Step 6：提交**

```bash
git add MobiFlow_Agent/README.md \
  docs/superpowers/specs/2026-07-20-pillar2-waypoint-scheduling-design.md \
  MobiFlow_Agent/tests/waypoint/test_platform_sequence_contract.py
git commit -m "docs: document sequence catalog and drafting boundary"
```

若跨契约测试在本任务没有实际修改，不要把它放入 `git add`。

---

## 3. 验收矩阵

| 能力 | 正向验收 | 失败/隔离验收 |
|---|---|---|
| 默认 catalog | 随包解析两条版本化序列 | 运行目录变化不影响资源查找 |
| 自定义 catalog | 按 ID 确定性 list/resolve | 非法 JSON/schema/ID/重复 ID 原子失败 |
| 可变状态 | 每次 resolve 得到等价模型 | 调用方 mutation 不污染目录或其他结果 |
| parser | 自然语言/遗留脚本文本得到 TestCase | 无 runtime/模型失败要求澄清 |
| waypoint decomposition | 生成有序、唯一的航点候选 | 空航点/空 outcome/越权 action 被拒绝 |
| assertion synthesis | 每航点至少一个可观察 check | 未知 fact、空 predicate 不形成半成品 |
| identity ownership | request metadata 原样进入 sequence | 模型无法覆盖 ID/behavior/profile |
| draft safety | READY sequence 可通过 Pydantic | 非 READY 时 sequence 恒为 `None` |
| catalog safety | draft 前后目录不变 | 无 save/add/delete API |
| P2-2 compatibility | 同 ID/profile/waypoint IDs 与 contract fixture 一致 | Platform 不新增目录或 AI 依赖 |

---

## 4. Definition of Done

- `SequenceCatalog.default()` 从安装包资源加载至少两条人工维护的 `.vN` 序列。
- `list_sequences()` 输出稳定排序摘要；`resolve_sequence()` 未知 ID 返回结构化错误。
- catalog 对非法源全量、原子失败，不提供隐式降级或部分加载。
- resolve 结果通过深拷贝隔离，mutation-isolation 测试通过。
- `draft_sequence` 同时支持自然语言与遗留脚本文本 source kind。
- draft 复用 `TestCaseParser` 与逐航点 `AssertionSynthesizer`，不错误复用全局 `TestCaseAssembler`。
- 每个航点拥有独立、可观察、target ID 对齐的 `VerificationSpec`。
- 模型不能决定或覆盖 `sequence_id`、`behavior_label`、`profile_package`。
- draft 不自动写目录、不创建 session/run、不调用 Platform 工具、不触发设备动作。
- 非完整草稿不以可执行 `WaypointSequence` 返回；issues/questions/trace refs 可诊断。
- JSON package data 在本地和安装态均可发现。
- Agent 全量测试、waypoint/graph/platform targeted 回归全部通过且无新增 skip。
- 总体设计与 P2-2 协议对 resolve/draft 的分层描述一致。

---

## 5. 明确后置

- **P2-2 验证收口：** Docker 环境实际执行 V10/V11、MySQL 唯一键、行锁和 pinned claim；它是发布置信门，不在本 Agent-only 计划中伪报完成。
- **P2-3b：** `CollectionIntent → IntentPlanner → DispatchPlan`、selector 编译期校验、设备存在性查询、类型化调用 `create_heterogeneous_run`。
- **P2-3c：** 定义 `WaypointEvidencePublisher` capability，把 `runTargetId/attemptId` 带入 TaskGraph 生命周期并自动发布 terminal attempt timeline。
- **P2-3d：** sequence/behavior/timeline 只读展示、异构创建 UI、草稿人工编辑和入库流程。
- **支柱三：** `rendezvous` 的跨设备 barrier 语义。
- **支柱四：** 航点内动作级时间线、`verdict/path_action_count` 和更细 pcap 标注。
