# P2-1c 航点序列接入 runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让用户能把一条 `WaypointSequence` 通过 `create_session` 注入,使它编译成 `TaskPlan` 并被 `TaskGraphRuntime` 真正执行(而非只由 PlannerAgent 动态产 plan);并把 `behavior_label` 结构化保存到 `TaskPlan`,为后续流量对齐做准备。

**Architecture:** 三步。(1) 给 `TaskPlan` 加可选字段 `behavior_label`,编译器 `compile_sequence_to_plan` 填充它。(2) `create_session`(Mixin + runtime 覆写两处签名)新增可选参数 `waypoint_sequence: WaypointSequence | None`,内部调 `compile_sequence_to_plan` 把编译结果存入 `session.plan`,`current_step` 保持 None。(3) 端到端验证:注入序列 → `run()` → 现有 `ensure_plan` 的 `if session.plan is None` 守卫会因 plan 已存在而走 `else` 分支跳过 planner、直接 `_activate_step(0)` 执行航点。

**Tech Stack:** Python 3.11+、pydantic v2(`StrictModel`)、LangGraph、pytest。

## Global Constraints

- 复用已验证机制:`ensure_plan`(`graph/nodes.py:65`)已有 `if session.plan is None:` 守卫——plan 已存在则走 else 跳过 planner。**本计划不改图节点、不改 ensure_plan/_initialize_plan**,只利用该既有守卫。
- `create_session` 有**两处签名**:`TaskGraphSessionSupportMixin.create_session`(`graph/session_support.py:73-94`)与 `TaskGraphRuntime.create_session` 覆写(`graph/runtime.py:61-80`,纯转发)。加参数必须**两处都改**,否则 runtime 层吞掉新参数。
- 注入路径下 `session.current_step` 必须保持 `None`(不在 create_session 里预激活)——`TaskSession` validator(`task/session.py:66`)允许 "plan 存在 + current_step=None",靠 `run→ensure_plan→else→_activate_step(0)` 激活首 step。
- `behavior_label: str | None = None` 加到 `TaskPlan`,为可选默认字段(不破坏现有关键字构造点,不触发 extra="forbid")。
- 复用 `compile_sequence_to_plan`(`waypoint/compiler.py`)、`WaypointSequence`(`waypoint/models.py`)。
- 测试运行:在 `MobiFlow_Agent/` 目录下 `python -m pytest -q`。
- 本计划不做时间戳采集 / 航点段时间线(那是 P2-1d);不碰 Platform/Java。

---

## File Structure

- Modify: `mobiflow_agent/task/plan.py` — `TaskPlan` 加 `behavior_label: str | None = None`
- Modify: `mobiflow_agent/waypoint/compiler.py` — `compile_sequence_to_plan` 填 `behavior_label=sequence.behavior_label`
- Modify: `tests/waypoint/test_waypoint_compiler.py` — 断言编译产物带 behavior_label
- Modify: `mobiflow_agent/graph/session_support.py` — Mixin.create_session 加 `waypoint_sequence` 参数
- Modify: `mobiflow_agent/graph/runtime.py` — runtime.create_session 覆写同步加参数并转发
- Test: `tests/graph/test_waypoint_session_integration.py`(Create) — 端到端:注入序列→run→航点被执行

---

## Task 1: TaskPlan 加 behavior_label + 编译器填充

**Files:**
- Modify: `mobiflow_agent/task/plan.py`
- Modify: `mobiflow_agent/waypoint/compiler.py`
- Modify: `tests/waypoint/test_waypoint_compiler.py`

**Interfaces:**
- Consumes: `WaypointSequence.behavior_label`(`waypoint/models.py`)。
- Produces: `TaskPlan.behavior_label: str | None = None`;`compile_sequence_to_plan` 产出的 plan 带 `behavior_label=sequence.behavior_label`。

- [ ] **Step 1: 写失败测试**

在 `tests/waypoint/test_waypoint_compiler.py` 末尾新增(复用文件已有的 `_sequence()` helper,它的 behavior_label 是 `"shopping_checkout"`):

```python
def test_compiled_plan_carries_behavior_label():
    plan = compile_sequence_to_plan(_sequence())
    assert plan.behavior_label == "shopping_checkout"
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/waypoint/test_waypoint_compiler.py::test_compiled_plan_carries_behavior_label -q`
Expected: FAIL —— `TaskPlan` 尚无 `behavior_label` 字段(extra="forbid" 使 `compile_sequence_to_plan` 传该关键字时报错,或 `plan.behavior_label` AttributeError)。注意:此步失败也可能发生在编译器还没传该参数——先加字段(Step 3a)再让编译器传(Step 3b),两处都改后测试才通过。

- [ ] **Step 3: 加字段 + 编译器填充**

(a) `mobiflow_agent/task/plan.py` 的 `TaskPlan` 类,在 `steps: list[TaskStep] = Field(default_factory=list)` 之后新增一行:

```python
    behavior_label: str | None = None
```

(不改 validator,它只校验 steps。)

(b) `mobiflow_agent/waypoint/compiler.py` 的 `compile_sequence_to_plan`,给 `TaskPlan(...)` 构造新增 `behavior_label=sequence.behavior_label`:

```python
def compile_sequence_to_plan(sequence: WaypointSequence) -> TaskPlan:
    return TaskPlan(
        plan_id=build_task_plan_id(),
        summary=(
            f"Waypoint sequence {sequence.sequence_id} "
            f"for behavior {sequence.behavior_label}."
        ),
        behavior_label=sequence.behavior_label,
        steps=[_compile_step(wp) for wp in sequence.waypoints],
    )
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/waypoint/test_waypoint_compiler.py -q`
Expected: PASS(含新测试,原有测试不受影响)

- [ ] **Step 5: 提交**

```bash
git add mobiflow_agent/task/plan.py mobiflow_agent/waypoint/compiler.py tests/waypoint/test_waypoint_compiler.py
git commit -m "feat(task): add behavior_label to TaskPlan; compiler populates it from sequence"
```

---

## Task 2: create_session 接入 waypoint_sequence

**Files:**
- Modify: `mobiflow_agent/graph/session_support.py`
- Modify: `mobiflow_agent/graph/runtime.py`
- Test: `tests/graph/test_waypoint_session_integration.py`(Create)

**Interfaces:**
- Consumes: `WaypointSequence`、`compile_sequence_to_plan`(`mobiflow_agent.waypoint`)。
- Produces: `create_session(..., waypoint_sequence: WaypointSequence | None = None)`(两处签名);传入时 `session.plan = compile_sequence_to_plan(waypoint_sequence)`,`session.current_step` 保持 None。

- [ ] **Step 1: 写失败测试(仅 create_session 层,不 run)**

Create `tests/graph/test_waypoint_session_integration.py`:

```python
from mobiflow_agent.common.contracts import (
    EntityKind,
    VerificationCheck,
    VerificationSpec,
)
from mobiflow_agent.graph import TaskGraphRuntime
from mobiflow_agent.waypoint import Waypoint, WaypointSequence


def _arrival_spec(waypoint_id: str) -> VerificationSpec:
    return VerificationSpec(
        verification_id=f"verification:{waypoint_id}",
        target_kind=EntityKind.TASK,
        target_id=waypoint_id,
        success_checks=[
            VerificationCheck(
                check_id=f"{waypoint_id}-check",
                description="Arrived.",
                evidence_hint="hint",
            )
        ],
    )


def _sequence() -> WaypointSequence:
    return WaypointSequence(
        sequence_id="shopping.checkout.v1",
        behavior_label="shopping_checkout",
        profile_package="com.example.shop",
        waypoints=[
            Waypoint(
                waypoint_id="logged_in",
                description="Reach logged-in state.",
                arrival_spec=_arrival_spec("logged_in"),
            ),
            Waypoint(
                waypoint_id="ordered",
                description="Reach order-placed state.",
                arrival_spec=_arrival_spec("ordered"),
            ),
        ],
    )


def test_create_session_from_waypoint_sequence_sets_plan():
    runtime = TaskGraphRuntime()
    session = runtime.create_session(
        "Collect shopping checkout traffic.",
        target_kind=EntityKind.TASK,
        target_id="shopping_checkout",
        waypoint_sequence=_sequence(),
    )
    assert session.plan is not None
    assert session.plan.behavior_label == "shopping_checkout"
    assert [step.step_id for step in session.plan.steps] == ["logged_in", "ordered"]
    # current_step 尚未激活(留给 run→ensure_plan)
    assert session.current_step is None


def test_create_session_without_sequence_leaves_plan_none():
    runtime = TaskGraphRuntime()
    session = runtime.create_session(
        "No sequence provided.",
        target_kind=EntityKind.TASK,
        target_id="x",
    )
    assert session.plan is None
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/graph/test_waypoint_session_integration.py -q`
Expected: FAIL —— `TypeError: create_session() got an unexpected keyword argument 'waypoint_sequence'`

- [ ] **Step 3: 改 Mixin.create_session**

在 `mobiflow_agent/graph/session_support.py`:

(a) 顶部 import 区新增(与其它 import 并列):

```python
from mobiflow_agent.waypoint import WaypointSequence, compile_sequence_to_plan
```

> 循环 import 检查:`waypoint/__init__.py` → `compiler` → `task/plan`;`session_support.py` 已依赖 `task` 层。`waypoint` 不依赖 `graph` 层,故 `graph/session_support.py` import `waypoint` 无环。Step 5 有 import 冒烟验证。

(b) `create_session` 签名(第 73-83)新增参数 `waypoint_sequence`,并在构造 session 后、返回前填充 plan:

```python
    def create_session(
        self,
        goal: str,
        *,
        target_kind: EntityKind | None = None,
        target_id: str | None = None,
        proposal: ExecutionProposal | None = None,
        verification_spec: VerificationSpec | None = None,
        session_id: str | None = None,
        handoff: ContextHandoff | None = None,
        waypoint_sequence: WaypointSequence | None = None,
    ) -> TaskSession:
        session = TaskSession(
            session_id=session_id or build_task_session_id(),
            goal=goal,
            target_kind=target_kind,
            target_id=target_id,
            initial_proposal=proposal,
            initial_verification_spec=verification_spec,
        )
        if waypoint_sequence is not None:
            session.plan = compile_sequence_to_plan(waypoint_sequence)
        if handoff is not None:
            self.apply_context_handoff(session, handoff)
        return session
```

> 注意:`session.plan` 赋值后 `current_step` 仍为 None、`current_step_index` 默认 0——满足 `TaskSession` validator(`task/session.py:66` 只禁止 current_step 非空但 plan 为空的反向情况;plan 存在 + current_step=None 合法)。

- [ ] **Step 4: 改 runtime.create_session 覆写**

在 `mobiflow_agent/graph/runtime.py` 的 `create_session` 覆写(第 61-80),签名加同名参数并转发:

```python
    def create_session(
        self,
        goal: str,
        *,
        target_kind: EntityKind | None = None,
        target_id: str | None = None,
        proposal: ExecutionProposal | None = None,
        verification_spec: VerificationSpec | None = None,
        session_id: str | None = None,
        handoff: ContextHandoff | None = None,
        waypoint_sequence: WaypointSequence | None = None,
    ) -> TaskSession:
        return super().create_session(
            goal,
            target_kind=target_kind,
            target_id=target_id,
            proposal=proposal,
            verification_spec=verification_spec,
            session_id=session_id,
            handoff=handoff,
            waypoint_sequence=waypoint_sequence,
        )
```

需要在 `runtime.py` 顶部 import `WaypointSequence`(供类型注解):检查文件是否已 import;若无,新增:

```python
from mobiflow_agent.waypoint import WaypointSequence
```

- [ ] **Step 5: 运行确认通过 + import 冒烟**

Run: `python -m pytest tests/graph/test_waypoint_session_integration.py -q`
Expected: PASS(2 passed)

Run: `python -c "import mobiflow_agent.graph.runtime; import mobiflow_agent.graph.session_support; import mobiflow_agent.waypoint"`
Expected: 无输出、无异常。若 ImportError(循环依赖),停止并报告。

- [ ] **Step 6: 提交**

```bash
git add mobiflow_agent/graph/session_support.py mobiflow_agent/graph/runtime.py tests/graph/test_waypoint_session_integration.py
git commit -m "feat(graph): accept waypoint_sequence in create_session, compile into session.plan"
```

---

## Task 3: 端到端 —— 注入序列后 run 真正执行航点

**Files:**
- Modify: `tests/graph/test_waypoint_session_integration.py`(追加端到端测试)

**Interfaces:**
- Consumes: Task 2 的 `create_session(..., waypoint_sequence=...)`;`TaskGraphRuntime.run`;注入式 agents(`ObserverAgent`/`StepPolicyAgent`/`VerifierAgent`/`RecoveryAgent`)。
- Produces: 验证注入序列的 session 经 `run()` 后,plan 未被 planner 覆盖、航点按 step 执行、任务完成。

- [ ] **Step 1: 写端到端测试**

在 `tests/graph/test_waypoint_session_integration.py` 追加。构造一个单航点序列,注入 step_policy 让该航点直接 STEP_SUCCEEDED,断言 run 后任务完成且执行的是航点序列的 step(step_id == 航点 id),证明 planner 被跳过(behavior_label 仍在,若 planner 介入会用它自己的 plan、behavior_label 为 None)。

```python
from mobiflow_agent.agents.observer import ObserverAgent
from mobiflow_agent.agents.recovery import RecoveryAgent
from mobiflow_agent.agents.step_policy import StepPolicyAgent
from mobiflow_agent.agents.verifier import VerifierAgent
from mobiflow_agent.agents.contracts import StepDecision, StepDecisionType
from mobiflow_agent.common.contracts import (
    EntityKind as _EntityKind,
    ObservationFact,
    ObservationFactSource,
    ObservationView,
)
from mobiflow_agent.task.status import TaskStatus


def _single_sequence() -> WaypointSequence:
    return WaypointSequence(
        sequence_id="wechat.text_chat.v1",
        behavior_label="wechat_text_chat",
        profile_package="com.tencent.mm",
        waypoints=[
            Waypoint(
                waypoint_id="message_sent",
                description="Send a text message.",
                arrival_spec=_arrival_spec("message_sent"),
            )
        ],
    )


def test_run_executes_injected_waypoint_sequence_skipping_planner():
    def observe(_session):
        return ObservationView(
            observation_id="obs-1",
            focus_kind=_EntityKind.TASK,
            focus_id="message_sent",
            facts=[
                ObservationFact(
                    fact_id="mobile_observation_summary",
                    source=ObservationFactSource.PLATFORM,
                    title="Mobile observation summary",
                    value={"screen_id": "chat"},
                )
            ],
        )

    def decide(_session):
        return StepDecision(
            decision_id="d1",
            decision_type=StepDecisionType.STEP_SUCCEEDED,
            summary="Message sent; waypoint reached.",
        )

    runtime = TaskGraphRuntime(
        observer_agent=ObserverAgent(observation_provider=observe),
        step_policy_agent=StepPolicyAgent(step_policy=decide),
        verifier_agent=VerifierAgent(),
        recovery_agent=RecoveryAgent(),
    )

    session = runtime.create_session(
        "Collect wechat text chat traffic.",
        target_kind=_EntityKind.TASK,
        target_id="message_sent",
        waypoint_sequence=_single_sequence(),
    )
    completed = runtime.run(session)

    # planner 被跳过:plan 仍是注入的航点序列编译产物
    assert completed.plan is not None
    assert completed.plan.behavior_label == "wechat_text_chat"
    assert [s.step_id for s in completed.plan.steps] == ["message_sent"]
    # 执行到了该航点
    assert completed.current_step is not None
    assert completed.current_step.step_id == "message_sent"
    assert completed.status == TaskStatus.COMPLETED
```

> 说明:注入序列后 `session.plan` 已非 None → `ensure_plan` 走 else 分支 `_activate_step(0)`、不调 planner。若断言 `behavior_label == "wechat_text_chat"` 成立,即证明执行的是注入的航点 plan 而非 planner 新建的 plan(planner 产物无 behavior_label)。VerifierAgent() 无参默认对 success_checks 的 evidence_hint 做匹配;observe 提供的 fact 需能让 verifier 判 VERIFIED_SUCCESS —— 若默认 verifier 无法通过,改用能通过的最小 observation 或注入 verifier 回调(参照 tests/graph/test_task_graph_runtime.py 里 STEP_SUCCEEDED 成功链的现有构造)。

- [ ] **Step 2: 运行确认通过**

Run: `python -m pytest tests/graph/test_waypoint_session_integration.py::test_run_executes_injected_waypoint_sequence_skipping_planner -q`
Expected: PASS。若 verifier 未能判成功导致未 COMPLETED,按上面 note 调整 observation/verifier 使其走通成功路径(参照现有 test_task_graph_runtime.py 的 observe→verify 成功链),不要放松对"plan.behavior_label / step_id / planner 被跳过"的核心断言。

- [ ] **Step 3: 全量回归**

Run: `python -m pytest -q`
Expected: 全绿,无回归。

- [ ] **Step 4: 提交**

```bash
git add tests/graph/test_waypoint_session_integration.py
git commit -m "test(graph): e2e — injected waypoint sequence runs and bypasses planner"
```

---

## 后续计划(不在本计划范围)

- **P2-1d**:步骤级时间戳采集(给 `TaskGraphRuntime` 注入 `clock: Callable[[],int]=build_memory_timestamp_ms`,照 `suite_runner` 先例;在 `_activate_step`/`_complete_step` 采进入/到达时间戳,挂到 `StepContextSummary` 或新载体)+ 航点段时间线导出(`trace_export.py` 新增 `waypoint_segments`,设备无关,含 `waypoint_id`/`behavior_label`/进入-到达时间戳/verdict)。
- **P2-2**:Platform(Java)异构分派。
- **P2-3**:对话入口 + Platform join deviceId 到航点时间线。
