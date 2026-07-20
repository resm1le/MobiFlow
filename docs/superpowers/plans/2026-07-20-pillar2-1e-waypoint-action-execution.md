# P2-1e 修复航点动作执行真空 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复航点无法执行动作的真空——编译器把每个航点 step 的 `allowed_side_effects` 编成 `[]`,导致 decide_step 的 allowlist 拦截所有执行提案。让 `Waypoint` 声明 `allowed_actions`(默认兜底为动作全集),编译器透传到 step,使航点能真正执行动作在航点间铺路。顺带消除三份重复的 `DEFAULT_MOBILE_ACTIONS` 常量。

**Architecture:** 三步。(1) 把 `DEFAULT_MOBILE_ACTIONS`(`["mobile.launch","mobile.tap","mobile.input_text","mobile.wait","mobile.back"]`)提升到 `common/contracts.py`,`intake/templates.py`、`agents/planner.py` 改为引用它(纯重构,保持行为)。(2) `Waypoint` 加 `allowed_actions: list[str]`,默认 `default_factory=lambda: list(DEFAULT_MOBILE_ACTIONS)`(非空全集,与 Planner 一致);编译器 `_compile_step` 的 `allowed_side_effects=[]` 改为 `allowed_side_effects=list(waypoint.allowed_actions)`。(3) 端到端:构造允许某 mobile 动作的航点,step_policy 提该动作,验证 EXECUTOR 被触发(动作真正执行,而非被拦去 recover)。

**Tech Stack:** Python 3.11+、pydantic v2(`StrictModel`)、LangGraph、pytest。

## Global Constraints

- `DEFAULT_MOBILE_ACTIONS` 值固定为 `["mobile.launch", "mobile.tap", "mobile.input_text", "mobile.wait", "mobile.back"]`(逐字,与现有三份一致)。提升到 `common/contracts.py` 后加入其 `__all__`。
- 重构保持行为:`intake/templates.py` 的 `DEFAULT_MOBILE_ACTIONS` 和 `agents/planner.py` 的 `PlannerAgent.DEFAULT_DYNAMIC_SIDE_EFFECTS` 改为引用 common 的常量,但**对外可见的名字/值不变**(templates 的模块级 `DEFAULT_MOBILE_ACTIONS` 名保留;`PlannerAgent.DEFAULT_DYNAMIC_SIDE_EFFECTS` 类属性名保留,值等于 common 常量)。
- `Waypoint.allowed_actions` 默认非空(兜底全集),使未声明的航点开箱即能执行动作——这是本次修复的核心目的,不能默认空列表。
- 动作名格式:`mobile.*` 点分工具名,与 `SUPPORTED_SIMULATED_ACTIONS`(`platform/simulation/adapter.py`)对齐。
- 复用现有:`compile_sequence_to_plan`/`_compile_step`(`waypoint/compiler.py`)、decide_step 的 allowlist(不改)、`TaskStep.allowed_side_effects`(不改语义)。
- 测试运行:在 `MobiFlow_Agent/` 目录下 `python -m pytest -q`。
- 本计划不改 decide_step / path_guard / 图路由;不做时间戳/时间线(P2-1d);不碰 Platform/Java。

---

## File Structure

- Modify: `mobiflow_agent/common/contracts.py` — 新增模块级 `DEFAULT_MOBILE_ACTIONS` + 加入 `__all__`
- Modify: `mobiflow_agent/intake/templates.py` — 改为从 common 引用(re-export 保持模块级名字可用)
- Modify: `mobiflow_agent/agents/planner.py` — `DEFAULT_DYNAMIC_SIDE_EFFECTS` 引用 common 常量
- Modify: `mobiflow_agent/waypoint/models.py` — `Waypoint` 加 `allowed_actions` 字段
- Modify: `mobiflow_agent/waypoint/compiler.py` — `_compile_step` 透传 allowed_actions
- Modify: `tests/waypoint/test_waypoint_models.py` — 断言 allowed_actions 默认全集 + 可自定义
- Modify: `tests/waypoint/test_waypoint_compiler.py` — 断言编译产物 allowed_side_effects 来自 waypoint
- Test: `tests/graph/test_waypoint_action_execution.py`(Create) — 端到端:航点执行动作

---

## Task 1: 提升 DEFAULT_MOBILE_ACTIONS 到 common(消重,保持行为)

**Files:**
- Modify: `mobiflow_agent/common/contracts.py`
- Modify: `mobiflow_agent/intake/templates.py`
- Modify: `mobiflow_agent/agents/planner.py`
- Test: `tests/common/test_default_mobile_actions.py`(Create)

**Interfaces:**
- Produces: `mobiflow_agent.common.contracts.DEFAULT_MOBILE_ACTIONS: list[str]`(模块级常量);`intake.templates.DEFAULT_MOBILE_ACTIONS` 与 `PlannerAgent.DEFAULT_DYNAMIC_SIDE_EFFECTS` 引用它、值不变。

- [ ] **Step 1: 写失败测试(常量在 common + 三处一致)**

Create `tests/common/test_default_mobile_actions.py`:

```python
from mobiflow_agent.common.contracts import DEFAULT_MOBILE_ACTIONS


def test_default_mobile_actions_value():
    assert DEFAULT_MOBILE_ACTIONS == [
        "mobile.launch",
        "mobile.tap",
        "mobile.input_text",
        "mobile.wait",
        "mobile.back",
    ]


def test_templates_and_planner_reference_common_constant():
    from mobiflow_agent.intake.templates import DEFAULT_MOBILE_ACTIONS as TEMPLATES_ACTIONS
    from mobiflow_agent.agents.planner import PlannerAgent

    assert TEMPLATES_ACTIONS == DEFAULT_MOBILE_ACTIONS
    assert PlannerAgent.DEFAULT_DYNAMIC_SIDE_EFFECTS == DEFAULT_MOBILE_ACTIONS
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/common/test_default_mobile_actions.py -q`
Expected: FAIL —— `ImportError: cannot import name 'DEFAULT_MOBILE_ACTIONS' from 'mobiflow_agent.common.contracts'`

- [ ] **Step 3: 在 common 定义常量**

在 `mobiflow_agent/common/contracts.py`,合适位置(如靠近文件顶部的其它模块级定义之后、或 `EntityKind` 附近)新增:

```python
DEFAULT_MOBILE_ACTIONS = ["mobile.launch", "mobile.tap", "mobile.input_text", "mobile.wait", "mobile.back"]
```

并在文件末尾的 `__all__`(第 248 行起)列表里加入字符串 `"DEFAULT_MOBILE_ACTIONS"`。

- [ ] **Step 4: templates.py 改为引用 common**

在 `mobiflow_agent/intake/templates.py`:
- 删除本地定义 `DEFAULT_MOBILE_ACTIONS = [...]`(第 10 行)。
- 在 import 区新增 `DEFAULT_MOBILE_ACTIONS` 到已有的 `from mobiflow_agent.common.contracts import ...`(第 7 行那句)。改为:

```python
from mobiflow_agent.common.contracts import ApprovalMode, DEFAULT_MOBILE_ACTIONS, EntityKind, StrictModel
```

- `templates.py` 的 `__all__`(第 111 行)保留 `"DEFAULT_MOBILE_ACTIONS"`(现在它是 re-export 的 common 常量),使 `from mobiflow_agent.intake.templates import DEFAULT_MOBILE_ACTIONS` 仍可用。`ScenarioTemplate.allowed_actions` 的 `default_factory=lambda: list(DEFAULT_MOBILE_ACTIONS)`(第 21 行)不变(现在引用的是 re-export 的同一常量)。

- [ ] **Step 5: planner.py 改为引用 common**

在 `mobiflow_agent/agents/planner.py`:
- 确认顶部已从 `common.contracts` import(若已 import 其它符号,把 `DEFAULT_MOBILE_ACTIONS` 加入那句;否则新增 `from mobiflow_agent.common.contracts import DEFAULT_MOBILE_ACTIONS`)。
- 把类属性(第 36 行)`DEFAULT_DYNAMIC_SIDE_EFFECTS = ["mobile.launch", ...]` 改为引用 common(保持类属性名不变):

```python
    DEFAULT_DYNAMIC_SIDE_EFFECTS = DEFAULT_MOBILE_ACTIONS
```

> 说明:类属性指向同一 list 对象。planner.py:162/169 用 `self.DEFAULT_DYNAMIC_SIDE_EFFECTS` 只读引用,不 mutate,故共享同一 list 安全。

- [ ] **Step 6: 运行确认通过 + 全量回归**

Run: `python -m pytest tests/common/test_default_mobile_actions.py -q`
Expected: PASS(2 passed)

Run: `python -m pytest -q`
Expected: 全绿(重构保持行为,templates/planner 相关测试不回归)

- [ ] **Step 7: 提交**

```bash
git add mobiflow_agent/common/contracts.py mobiflow_agent/intake/templates.py mobiflow_agent/agents/planner.py tests/common/test_default_mobile_actions.py
git commit -m "refactor: hoist DEFAULT_MOBILE_ACTIONS to common, dedupe three copies"
```

---

## Task 2: Waypoint 加 allowed_actions + 编译器透传(修真空)

**Files:**
- Modify: `mobiflow_agent/waypoint/models.py`
- Modify: `mobiflow_agent/waypoint/compiler.py`
- Modify: `tests/waypoint/test_waypoint_models.py`
- Modify: `tests/waypoint/test_waypoint_compiler.py`

**Interfaces:**
- Consumes: `DEFAULT_MOBILE_ACTIONS`(`common.contracts`,Task 1)。
- Produces: `Waypoint.allowed_actions: list[str]`(默认 `list(DEFAULT_MOBILE_ACTIONS)`);`_compile_step` 产出的 `TaskStep.allowed_side_effects == waypoint.allowed_actions`。

- [ ] **Step 1: 写失败测试**

在 `tests/waypoint/test_waypoint_models.py` 追加(文件已有 `_waypoint`/`_arrival_spec` 等 helper,复用):

```python
from mobiflow_agent.common.contracts import DEFAULT_MOBILE_ACTIONS


def test_waypoint_allowed_actions_defaults_to_full_mobile_set():
    wp = _waypoint("logged_in")
    assert wp.allowed_actions == DEFAULT_MOBILE_ACTIONS


def test_waypoint_allowed_actions_can_be_narrowed():
    wp = Waypoint(
        waypoint_id="tap_only",
        description="Only tapping allowed.",
        arrival_spec=_arrival_spec("tap_only"),
        allowed_actions=["mobile.tap"],
    )
    assert wp.allowed_actions == ["mobile.tap"]
```

在 `tests/waypoint/test_waypoint_compiler.py` 追加(复用文件已有 `_sequence` helper):

```python
from mobiflow_agent.common.contracts import DEFAULT_MOBILE_ACTIONS


def test_compiled_step_allowed_side_effects_from_waypoint_default():
    plan = compile_sequence_to_plan(_sequence())
    assert plan.steps[0].allowed_side_effects == DEFAULT_MOBILE_ACTIONS


def test_compiled_step_allowed_side_effects_narrowed():
    seq = WaypointSequence(
        sequence_id="narrow.v1",
        behavior_label="narrow",
        profile_package="pkg",
        waypoints=[
            Waypoint(
                waypoint_id="only_tap",
                description="Only tap.",
                arrival_spec=_arrival_spec("only_tap"),
                allowed_actions=["mobile.tap"],
            )
        ],
    )
    plan = compile_sequence_to_plan(seq)
    assert plan.steps[0].allowed_side_effects == ["mobile.tap"]
```

> 注意:`_arrival_spec` 在两个测试文件中都已定义;`Waypoint`/`WaypointSequence` 已在文件 import。若 `test_waypoint_models.py` 的 `_waypoint` helper 不接受额外参数,第一个测试直接用它即可(它构造的 waypoint 不传 allowed_actions,应得默认全集)。

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/waypoint/test_waypoint_models.py tests/waypoint/test_waypoint_compiler.py -q`
Expected: FAIL —— models 测试:`Waypoint` 无 `allowed_actions`(extra="forbid" 拒绝该关键字 / `wp.allowed_actions` AttributeError);compiler 测试:`allowed_side_effects` 仍是 `[]` 而非全集。

- [ ] **Step 3: Waypoint 加字段**

在 `mobiflow_agent/waypoint/models.py`:
- import 区第 9 行,把 `DEFAULT_MOBILE_ACTIONS` 加入 `from mobiflow_agent.common.contracts import ...`:

```python
from mobiflow_agent.common.contracts import DEFAULT_MOBILE_ACTIONS, PathConstraint, StrictModel, VerificationSpec
```

- `Waypoint` 类(第 24-30 行),在 `rendezvous` 之后新增字段:

```python
    allowed_actions: list[str] = Field(default_factory=lambda: list(DEFAULT_MOBILE_ACTIONS))
```

> `default_factory=lambda: list(...)` 每个实例得到独立副本,避免共享可变默认。

- [ ] **Step 4: 编译器透传**

在 `mobiflow_agent/waypoint/compiler.py` 的 `_compile_step`(第 15-28),把第 20 行:

```python
        allowed_side_effects=[],
```

改为:

```python
        allowed_side_effects=list(waypoint.allowed_actions),
```

- [ ] **Step 5: 运行确认通过**

Run: `python -m pytest tests/waypoint/test_waypoint_models.py tests/waypoint/test_waypoint_compiler.py -q`
Expected: PASS(含新测试)

- [ ] **Step 6: 提交**

```bash
git add mobiflow_agent/waypoint/models.py mobiflow_agent/waypoint/compiler.py tests/waypoint/test_waypoint_models.py tests/waypoint/test_waypoint_compiler.py
git commit -m "feat(waypoint): add allowed_actions (defaults to full mobile set), compile into allowed_side_effects"
```

---

## Task 3: 端到端 —— 航点真正执行一个动作(证明真空已修)

**Files:**
- Test: `tests/graph/test_waypoint_action_execution.py`(Create)

**Interfaces:**
- Consumes: Task 2 的 Waypoint.allowed_actions + create_session(waypoint_sequence)(P2-1c);注入式 agents。
- Produces: 验证注入航点序列(allowed_actions 允许某 mobile 动作)经 run 后,该动作提案通过 allowlist、EXECUTOR 角色被触发(而非被拦去 recover)。

- [ ] **Step 1: 写端到端测试**

Create `tests/graph/test_waypoint_action_execution.py`。构造一个航点(默认 allowed_actions 全集,含 mobile.tap),step_policy 第一次提 mobile.tap 执行、第二次判 STEP_SUCCEEDED;用一个记录调用的 fake executor adapter 断言"该动作真的被执行了"。

参照 `tests/graph/test_task_graph_runtime.py` 中 `executor_agent=ExecutorAgent(adapter)` 的现有成功链构造(如 line 241-270 附近),复用其 `_proposal`/`_verification_spec`/`_build_observation`/`_step_decision` 及 fake adapter 模式(在该测试文件里找到用于 executor 的 fake adapter 类,导入或仿照构造)。

核心断言(不放松):
- `AgentRole.EXECUTOR` 出现在 `completed.role_results` 的角色序列里(证明动作到达执行,而非被 allowlist 拦去 recover)。
- `completed.last_execution_result is not None`(执行结果被记录)。
- 对照:该航点的 `allowed_side_effects` 含 `mobile.tap`(通过默认全集),故提案通过 allowlist。

具体测试代码需实现者依据 test_task_graph_runtime.py 的现有 executor 成功链范例编写(fake adapter 返回 EXECUTED 的 GovernedActionResult),确保:
1. 用 `create_session(..., waypoint_sequence=<含默认 allowed_actions 的序列>)` 注入航点。
2. step_policy 回调第一次返回 `PROPOSE_EXECUTION` + 一个 `action_tool_name="mobile.tap"` 的 proposal(arguments 非空),第二次返回 `STEP_SUCCEEDED`。
3. `ExecutorAgent(fake_adapter)`,fake_adapter 记录 submit_execution_proposal 被调用。
4. run 后断言上述核心断言 + fake_adapter 确实被调用过(执行发生)。
5. **对照子测试(证明修复必要性)**:同样构造但航点 `allowed_actions=[]`(显式空),断言该 mobile.tap 提案被拦(EXECUTOR 不出现 / 走 recover)——证明是 allowed_actions 让动作得以执行。

> 实现提示:proposal 的 action_tool_name 必须在 step 的 allowed_side_effects 内才通过 decide_step:145 的 allowlist。默认全集含 mobile.tap,故通过;对照组空列表则被拦。executor 的 fake adapter 参照现有 test 的 adapter(返回 GovernedActionResult(state=EXECUTED, ...))。若默认 VerifierAgent 影响完成态,聚焦断言放在"EXECUTOR 被触发 + adapter 被调用"上,不必强求 COMPLETED(执行发生即证明真空已修)。

- [ ] **Step 2: 运行确认通过**

Run: `python -m pytest tests/graph/test_waypoint_action_execution.py -q`
Expected: PASS。主测试证明航点动作被执行(EXECUTOR 触发 + adapter 调用);对照测试证明空 allowed_actions 会拦截(修复的必要性)。若构造上遇阻,参照 test_task_graph_runtime.py 现有 executor 成功链调整,但不放松"EXECUTOR 被触发 / 空列表被拦"这两个核心对照断言。

- [ ] **Step 3: 全量回归**

Run: `python -m pytest -q`
Expected: 全绿,无回归。

- [ ] **Step 4: 提交**

```bash
git add tests/graph/test_waypoint_action_execution.py
git commit -m "test(graph): e2e — waypoint executes an action; empty allowed_actions blocks it"
```

---

## 后续计划(不在本计划范围)

- **P2-1d**:步骤级时间戳采集(注入 clock)+ 航点段时间线导出。
- **P2-2**:Platform(Java)异构分派。
- **P2-3**:对话入口 + Platform join deviceId。
