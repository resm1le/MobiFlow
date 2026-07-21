# 支柱二设计:异构并行的语义航点序列调度

> 日期:2026-07-20
> 状态:草案,待 review 与负责人定稿
> 定位依据:`docs/superpowers/specs/2026-07-20-project-positioning-baseline.md`(四支柱之支柱二)
> 范围:本轮聚焦"从对话驱动、给不同设备下发不同任务的语义航点序列异构并行调度"。不含支柱三协同、UI、真机执行。

---

## 0. 背景与目标

MobiFlow 是流量采集研究的「移动端行为生成与调度引擎」:用 AI Agent 可靠地在移动设备上产生真实 App 使用行为,配合独立第三方流量采集器抓包。本轮目标是让**用户通过与 Agent 对话,把不同的采集任务并行下发到不同设备**,取代当前"同一 task 同构 fan-out 到全池"的模式;并把易失效的死脚本升级为**语义航点序列**,使采集在无人值守下更可靠、样本可复现可比对。

### 需求边界(9 条硬共识)

1. **系统入口**:Agent 是唯一入口,用户直接和 Agent 对话下发采集意图。UI 本轮不做,但设计需定义好 Agent 对话入口(接口层面),UI 作为后续独立小块预留。
2. **调度形态**:对话驱动,给不同设备下发**不同**任务(异构分派)。
3. **设备寻址(基于注册)**:设备经执行器 `POST /executor/register` 连上 platform 后有稳定标识 deviceId + 状态(registered/online/busy)。默认按条件/标签自动挑"已注册且空闲"设备,支持按注册标识点名。
4. **任务内容模型 = 语义航点序列**:脚本从"死操作序列"升级为"航点(目标状态)序列"。**一条航点序列 = 一种行为 = 采集器的一个标签**(例:微信「文字聊天」vs「视频通话」是两条序列/两个标签)。
5. **AI 职责 = 在航点间铺路**:抗中断(恢复广告/加载/跳错页等假障碍)、抗 UI 漂移(语义定位而非死坐标),**不做航点内自由探索**。行为链路大体一致、可复现可比对(硬指标)。
6. **失败策略 = 宁缺毋滥**:只能靠偏离标准路径硬凑才能到达航点时,判失败 + 结构化归因留证,绝不产生脏样本/脏标签。
7. **路径约束 + 校验强度 = 混合**:默认靠 AI 常识判断标准路径;可比性/标签敏感的关键航点(如视频通话"已接通")上显式路径约束 + 强到达校验,防标签串味。
8. **航点来源 = 混合**:支持手写精调 + AI 辅助生成草稿(可从现有死脚本反向提炼)。
9. **本轮范围**:仅支柱二。航点模型要能向支柱三(跨设备协同:A 发消息 B 收 / 视频通话双端)自然延伸——单设备序列是特例、协同是多序列在某些航点会合——但本轮不实现协同,只在模型上不堵死。

### 核心概念:"路径" vs "航点"

- **航点(waypoint)** = 一个语义目标状态(如"已登录""已搜索到商品""已下单"),本身不产生流量,只是状态标记。
- **路径(path)** = AI 在相邻两航点间的实际操作序列(点了哪些按钮、走了哪几屏)。**流量由路径产生,不由航点产生**。同一航点不同路径 → 流量截然不同 → 破坏可比性、污染标签。
- 核心张力:**航点保证"到达同样的状态",路径约束保证"用同样的方式到达"**。

---

## 1. 总体分层

| 层 | 本轮职责 | 复用/扩展的地基 |
|---|---|---|
| **Agent(Python)** | 航点序列的语义定义、编译、AI 铺路决策、失败判定 | `TaskGraphRuntime` 闭环、`VerificationSpec`、intake 流水线、`ExecutionTraceExporter` |
| **Platform(Java)** | 设备注册/寻址、异构分派、租约并发、批次聚合、证据落库 | `ExperimentRun/Target`、`claim/renewLease/LeaseReaper`、MCP `ToolFacadeService` |
| **执行器(Kotlin)** | 真机执行,本轮不碰 | 仅认 Platform 下发的 `taskPayloadJson` 契约 |

分层依据:航点"用什么方式走"是核心价值(可比样本)的判断逻辑,属 Agent;"多设备并发不抢占"是规模保障,属 Platform 已验证的租约地基,扩展不重造。真机是执行器责任边界,不阻塞 Agent/Platform 开发。

---

## 2. 航点序列数据模型(Agent 层定义,Platform 透传)

一条序列 = 一种行为 = 采集器一个标签。顶层结构:

```json
{
  "sequence_id": "wechat.text_chat.v1",
  "behavior_label": "wechat_text_chat",        // 绑采集器标签,序列级唯一
  "profile_package": "com.tencent.mm",
  "waypoints": [
    { "waypoint_id": "logged_in",
      "arrival_spec": { /* 复用 VerificationSpec */ },
      "strength": "commonsense",               // commonsense | strict
      "path_constraint": null },
    { "waypoint_id": "call_connected",
      "arrival_spec": { "success_checks": [ /* ... */ ] },
      "strength": "strict",
      "path_constraint": {                     // 关键航点显式约束
        "required_screens": ["chat", "call_dialog"],
        "forbidden_actions": ["search", "moments"] } }
  ]
}
```

**关键复用**:`arrival_spec` 直接就是现有 `VerificationSpec`(`success_checks` + 六元谓词 over 事实目录)——航点到达校验 = 已有 `VerifierAgent` 逻辑,零重造。航点段 = 现有 `plan` 的一个 step;整条序列即一个多步 plan,天然复用 `ensure_plan→activate_step→…→verify` 闭环,每个航点走一轮闭环。

**校验强度混合(需求 7)**:`strength=commonsense` 时只跑 `arrival_spec`;`strength=strict` 时额外校验 `path_constraint`(见 §5),防标签串味。

**向支柱三预留(需求 9,不实现)**:航点增可选字段 `rendezvous: {barrier_id, role}`,单设备序列中恒为 null;协同即多序列在同名 barrier 处会合。本轮 schema 容纳该字段但调度器忽略之。

---

## 3. 异构分派(Platform 层改造)

当前 `createRun` 同构:`selectRunDevices` 选全池 → 每台建相同 `task`。改造为**分派清单(dispatch plan)驱动**。

新增 MCP 工具 `create_heterogeneous_run`,入参为分派条目数组:

```json
{ "name": "collection-batch-01", "dispatch": [
  { "sequence_id": "wechat.text_chat.v1", "select": {"count":3, "requiredTags":["android13"]} },
  { "sequence_id": "wechat.video_call.v1", "select": {"deviceIds":["dev-7","dev-9"]} }
]}
```

实现:一个 `ExperimentRun` 挂多条 `ExperimentRunTarget`,**每个 target 携带各自的 `sequence_id` + `taskPayloadJson`**(不再全部取 `run.getTaskPayloadJson()`)。

- **模型扩展**:把"航点序列内容"下沉到 target/task 级。
  - `TaskEntity.taskPayloadJson` **已核实为 per-task 字段**(`PersistenceModels.java:264`,DB 列 `task_payload_json` 见 `TaskMapper.java:45`);当前 `createInitialTargetTask` 从 `run.getTaskPayloadJson()` 写入(`:417`),改为写该 target 对应序列的 payload 是真实可行的小改动。
  - `ExperimentRunTargetEntity` 增 `sequenceId` 是**真 schema 变更**(该 entity 现无此字段,`PersistenceModels.java:716-825`):需 entity + DB 迁移 + mapper 三处改。不是零成本,实现计划须列为独立步骤。
- **设备寻址(需求 3,含新增逻辑)**:每个 dispatch 条目按标签筛或按 `deviceIds` 点名。**注意两处非复用的新逻辑**(Review 核实):
  - **限量 `count` 是新增**:现 `selectRunDevices` 无 count/limit,返回**全部**匹配设备(`ExperimentRunService.java:441-444`)。`select:{count:3}` 的"取 N 台"需新写。
  - **跨条目去重是新增**:防同一设备被两序列争抢。**去重优先级需明确**:点名(`deviceIds`)优先占位,标签筛在剩余空闲设备中分配;两条目撞同一台时点名胜出。
- **空闲判定收紧(待定项 #2,已核实必要)**:现 `ExperimentRunSelectors.matchesPool` 只校验 registered/online/非 QUIESCED(`ExperimentRunSelectors.java:21-22`),**不过滤 `busy`**(`busy` 字段存在于 `PersistenceModels.java:132` 却未用)。异构点名极易撞 busy 设备,须补 `!busy` 过滤。
- **并发安全零改动**:分派只决定"建多少 target/task",实际抢占仍走 `findClaimableQueuedTasks`(`FOR UPDATE SKIP LOCKED` + `target_device_id` 匹配,`TaskMapper.java:65-70`)+ 租约。异构不影响并发正确性。

---

## 4. Agent 对话入口 → 调度(接口层,UI 后置)

定义**对话入口契约(需求 1)**,不实现 UI:

```
CollectionIntent(自然语言) → IntentPlanner(Agent) → DispatchPlan → DispatchPlanCompiler → governed proposal → MCP
```

`IntentPlanner` 输出 `DispatchPlan`。**DispatchPlan 必须有显式 schema 与非法输入契约**(Review 要求,否则无法据以实现):

```
DispatchPlan:
  name: str
  dispatch: list[DispatchEntry]   # 非空
DispatchEntry:
  sequence_id: str                # 必须能被 resolve_sequence 解析,否则拒绝
  select: DeviceSelector          # 二选一:{count:int>0, required_tags?, excluded_tags?} 或 {device_ids: [str] 非空}
```

非法输入处理(在 Agent 侧编译期拒绝,不下发 MCP):`sequence_id` 无法解析、`select` 两种模式混用或都空、`count<=0`、`device_ids` 含未注册设备 → 返回结构化错误给对话层,不建 run。NL → `sequence_id`/`select` 的映射由 `IntentPlanner` 负责；P2-3b 已落地"显式点名序列 + 显式设备条件"的受限自然语言，复杂 NL 解析后置。

落地调用序列:

1. `list_devices` + `get_run_planning_catalog`(现有)——获取设备快照、profile 能力与 Platform 默认 run/artifact policy；快照不是 reservation。
2. Agent `SequenceCatalog.resolve_sequence`(**已实现,确定性只读**):按完整版本 `sequence_id` 取正式序列定义。Platform 不复制目录或 Pydantic schema。
3. Agent `DispatchPlanCompiler`(**已实现**):校验 sequence/profile/device identity，并构造完整 `sequenceId + profilePackage + taskPayload + select`。
4. `propose_governed_action(actionToolName=create_heterogeneous_run)`(**已实现,side_effect + explicit 确认**):标准 Agent 入口统一复用 confirmation token；不新增 direct action adapter。
5. Platform 在批准执行时重新权威校验设备可用性、去重与容量，随后才创建 run。
6. `observe_run` / `get_run_target`(现有)——回报进度。

对话入口本轮以"Agent 编程接口 + Platform MCP 工具"呈现;UI 只是该接口的一个前端,预留、不做。若未来需要远程暴露 `resolve_sequence`/`draft_sequence`,只能增加指向 Agent 服务的薄代理,不能让 Platform 成为第二份序列权威。

**航点来源混合(需求 8)**:手写序列进入 Agent 随包版本化 JSON 目录;AI 辅助草稿由 Agent `SequenceDraftService` 复用 intake 流水线(`TestCaseParser→航点分解→逐航点 AssertionSynthesizer`)从自然语言/现有死脚本反向提炼 `arrival_spec`。`draft_sequence` 是 analyze 类只读编程接口,只产完整草稿和诊断;人工精调、评审后才能以新 `.vN` 文件入库,绝不自动写目录。

---

## 5. AI 铺路 + 失败判定(需求 5/6)

现有闭环 `dynamic_execute→verify→recover→verify_recovery` 已能区分"救活 vs 放弃",但**实现"宁缺毋滥"需改图路由,不是纯语义改造**(Review 核实,原草案低估了此项)。

- **假障碍(救活)**:广告/加载/跳错页 → `recover` 产出回到标准路径的纠偏动作(现 `RecoveryAgent` 已处理 `slow_loading_screen` 等 `blocked_reason`,`recovery.py:104`)。救活后仍在 `path_constraint` 内 → 继续。
- **偏离路径(判失败)—— 需新增终态出口**:现状 `decide_step`(`nodes.py:114-178`)对越界提案(已有 `allowed_side_effects` allowlist,`:144`)一律 `route_hint="recover"`(`:150`),**所有 block 都流经 recover→verify_recovery,没有"直接 failed"出口**。因此:
  - 新增 `PathConstraintGuard` 时,必须同时在路由上引入 `off_standard_path` 终态:让 `route_after_recover` / `verify_recovery` 把 `blocked_reason=off_standard_path` 识别为**不可救的终态失败**,而非再次尝试恢复。
  - **须厘清与现有 `allowed_side_effects` allowlist(`nodes.py:144`)的关系**:allowlist 已能拦越界 side-effect,PathConstraintGuard 与之部分重叠。实现时应说明是扩展该 allowlist 的判定(复用),还是并行的独立 guard——避免双重逻辑冲突。
- **`path_constraint` 判定依赖 screen 事实,须明确来源**(Review 指出的悬空点):`required_screens`/`forbidden_actions` 需要"当前在哪屏"的事实。该事实必须来自 observer 产出的事实目录(如 `mobile_observation_summary` / `simulated_screen_snapshot`),guard 从 observe 结果读取当前 screen 标识。实现前须确认仿真事实目录里有稳定的 screen 标识字段;若无,需先在 observer 侧补齐,否则约束无法判定。
- **强到达校验**:`strict` 航点额外要求 `arrival_spec` 全通过且路径日志无越界,任一不满足 → 失败 + 结构化归因,绝不产脏标签。

---

## 6. 流量对齐产物(需求 5)

目标产物:每航点段一条记录 `{waypoint_id, behavior_label, deviceId, entered_at, arrived_at, verdict, path_action_count}`,供事后按 `deviceId` + 时间窗与第三方 pcap 对齐。

**分层修正(Review 核实的 P0,原草案"扩展 _build_timeline"表述错误)**:
- `ExecutionTraceExporter._build_timeline`(`trace_export.py:161`)是**节点/状态级**,数据源为 `role_results`/`status_history`,**本身无 waypoint 边界、无 deviceId、无 behavior_label**。
- 更关键:**`deviceId` 是 Platform 侧 `target.deviceId` 概念,Agent 执行逻辑层根本不持有它**。让 Agent exporter 凭空透出 deviceId 属于把 Platform 数据错放到 Agent 层。
- **正确切分(已定稿:方案 A,deviceId 由 Platform 侧管理)**:
  - **Agent 层**产出**设备无关的航点段时间线**(`waypoint_id` + `behavior_label` + 进入/到达时间戳 + verdict + 动作计数)——这些是 Agent 自己拥有的执行事实,**不含 deviceId**。
  - **`deviceId` 由 Platform 层统一管理并 join**:Platform 在两端都掌握 deviceId(下发时分配、回报时落库),落库航点时间线时把 target.deviceId 与 Agent 上报的段时间线 join。Agent 保持设备无关,不被塞入设备身份。
  - (下发方向的"点名指定设备"是另一回事,见 §3 `select.device_ids`,不受此影响——deviceId 标签始终由 Platform 负责,Agent 两端都不碰。)
- 脱敏与导出沿用 `ExecutionTraceExporter` 现有能力;Platform 侧 `RunEvent`/artifact 落库最终航点时间线作为证据。

> 与支柱四关系:此产物即支柱四"细粒度动作-流量对齐"的粗粒度落点——航点边界即流量标注边界。更细粒度(航点内动作级)留待支柱四推进。

---

## 7. 测试策略(仿真优先)

- **异构分派(Platform,JUnit)**:仿真设备池,断言"3×X + 2×Y"生成 5 个 target 且 `sequenceId`/`taskPayloadJson` 各异;并发 claim 无重复抢占(复用现有租约测试)。
- **航点铺路 + 失败判定(Agent,仿真适配器)**:用 `platform/simulation/adapter.py` + `fake` adapter,构造假障碍事实序列 → 断言救活;构造仅越界可达 → 断言判 `off_standard_path` 失败。
- **端到端**:复用 intake 的 simulation suite runner,跑一条含 `strict` 航点的序列,校验 timeline 完整 + `distinct-session-id` 不变量。
- 真机不阻塞,执行器仅契约冒烟。

---

## 8. YAGNI 边界(本轮不做)

- 不做支柱三跨设备协同(仅 schema 预留 `rendezvous`,调度器忽略)。
- 不做 UI(仅定义对话入口接口)。
- 不做真机执行(执行器契约不变)。
- 不做航点内自由探索(需求 5 硬约束)。
- 不改租约/并发底层机制,只在其上加异构分派。
- 不引入序列库持久化的复杂版本管理(先文件/内存,`sequence_id` 带 `.vN` 即可)。

---

## 9. 已定稿决策(原待定项,负责人 2026-07-20 拍板)

1. **序列 payload 落库粒度**:全落 target/task 级,run 级 `taskPayloadJson` 留空/默认。
2. **空闲判定收紧**:`selectRunDevices` / `matchesPool` 强制过滤 `status=ONLINE && !busy`(采纳,`ExperimentRunSelectors.java:21-22` 补 `!busy`)。
3. **`path_constraint` 表达力**:先用 `required_screens`/`forbidden_actions` 黑白名单;实际遇到表达不了的约束时再升级谓词式(YAGNI)。
4. **§6 deviceId 归属**:方案 A——deviceId 由 Platform 侧统一管理,Agent 产设备无关时间线,Platform join。

---

## 10. 关键实现文件(供后续实现计划)

- `AI_Mobile_Executor_Platform/services/executor-control-service/src/main/java/com/example/platform/control/application/ExperimentRunService.java` — `createRun`/`selectRunDevices`/`createInitialTargetTask` 异构改造核心
- `AI_Mobile_Executor_Platform/services/executor-control-service/src/main/java/com/example/platform/control/application/ToolFacadeService.java` — 暴露受显式确认保护的 `create_heterogeneous_run`;只消费 Agent 已解析 payload
- `AI_Mobile_Executor_Platform/services/executor-control-service/src/main/java/com/example/platform/control/domain/PersistenceModels.java` — `ExperimentRunTargetEntity` 增 `sequenceId`、task payload per-target
- `MobiFlow_Agent/mobiflow_agent/waypoint/catalog.py` 与 `waypoint/sequences/*.json` — Agent 唯一权威的确定性版本化序列目录与 `resolve_sequence`
- `MobiFlow_Agent/mobiflow_agent/waypoint/drafting.py` — 只读 `draft_sequence`、航点分解与逐航点 assertion synthesis
- `MobiFlow_Agent/mobiflow_agent/collection/` — P2-3b 的受限意图规划、typed discovery capability、确定性 proposal 编译与治理提交
- `MobiFlow_Agent/mobiflow_agent/common/contracts.py` — 航点序列模型复用/扩展 `VerificationSpec`
- `MobiFlow_Agent/mobiflow_agent/graph/builder.py` 与 `MobiFlow_Agent/mobiflow_agent/runtime/trace_export.py` — 铺路/失败判定闭环 + 航点级 timeline 导出
- `MobiFlow_Agent/mobiflow_agent/graph/nodes.py` — `decide_step` 路由(`:114-178`,`allowed_side_effects` allowlist `:144`,`off_standard_path` 终态出口)
- `MobiFlow_Agent/mobiflow_agent/task/plan.py` — `TaskStep.verification_spec`(航点=step 复用点)
- `AI_Mobile_Executor_Platform/.../application/ExperimentRunSelectors.java` — `matchesPool` 补 `!busy` 空闲过滤

---

## 11. Review 修订记录(2026-07-20,独立评审后)

评审结论:方向正确、地基复用判断大体成立,**可进入实现计划阶段**。以下 5 处已按评审修订到正文:

| 严重度 | 问题 | 修订位置 |
|---|---|---|
| P0 | §6 分层越界:`deviceId` 是 Platform 概念,Agent exporter 不持有;"扩展 `_build_timeline`"表述错误 | §6 已重定分层:Agent 产航点段时间线,deviceId 由 Platform join 或改契约传入 |
| P0 | §3 设备寻址夸大复用:`selectRunDevices` 无 count、无跨条目去重,均为新增逻辑 | §3 已标明 count/去重为新增,并定去重优先级 |
| P1 | §5 失败判定与图路由冲突:现所有 block 流经 recover,无"直接 failed"出口 | §5 已补:须新增 `off_standard_path` 终态路由 + 厘清与 allowlist 关系 |
| P1 | §5 `path_constraint` 依赖的 screen 事实来源悬空 | §5 已补:screen 事实来自 observer 事实目录,实现前须确认字段存在 |
| P1 | §4 DispatchPlan 无 schema/非法输入契约,无法据以实现 | §4 已补 DispatchPlan schema + 编译期拒绝规则 |

评审同时确认成立的关键复用(无需改):`TaskEntity.taskPayloadJson` 确为 per-task 字段、航点=plan step(`TaskStep` 自带 `verification_spec`)、`arrival_spec`=`VerificationSpec`、六元谓词恰 6 个、claim/租约/`SKIP LOCKED` 并发安全、ToolFacadeService 工具注册模式、rendezvous 预留"不堵死"判断成立。三个待定项(§9)评审均认可建议方向。
