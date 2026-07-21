# P2-1d 步骤时间戳采集与航点段时间线 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让每个航点段的进入/到达时间戳被采集,并导出**设备无关**的"航点段时间线"(`waypoint_segments`),供事后与第三方流量抓包按时间对齐,兑现设计 §6 的流量对齐产物。

**Architecture:** 四步。(1) `TaskSession` 加 `waypoint_timings: dict[str, dict[str, int]]`(与 `step_summaries`/`step_policy_iterations` 同款 by-step_id dict 先例)。(2) `TaskGraphRuntime`/`TaskGraphSessionSupportMixin` 构造函数注入 `clock: Callable[[], int] = build_memory_timestamp_ms`(照 `TestSuiteRunner` 先例);`_activate_step` 采 `entered_at_ms`(用 `setdefault` 幂等,防复活场景覆盖),`_complete_step` 与 `_complete_step_without_verification` 都显式采 `arrived_at_ms`(**skip 路径无 refresh 触发,必须显式打点**)。(3) `ExecutionTraceExporter._build_waypoint_segments(session)` 从 `session.plan.behavior_label` + `session.plan.steps` + `session.waypoint_timings` 组装,`export_json` 挂 `payload["waypoint_segments"]`(不走 payload dict 中转,直接读 session)。(4) 端到端:注入序列 clock 化 run,断言 waypoint_segments 时序确定性。

**Tech Stack:** Python 3.11+、pydantic v2(`StrictModel`)、LangGraph、pytest。

## Global Constraints

- 时钟复用 `mobiflow_agent.memory.store.build_memory_timestamp_ms`(与 `TestSuiteRunner` 先例一致,`suite_runner.py:31`),**不提到 common**——第二处使用者,还不到共层化的抛物点。
- `waypoint_timings` 挂在 `TaskSession` 上,**不挂 `StepContextSummary`**——`summarize_current_step` 每次全字段重建 + `refresh_session_context` 无条件覆盖(`service.py:65`),挂 summary 会被冲。
- `entered_at_ms` 用 `setdefault` 幂等写入(防复活/重试场景覆盖真实第一次进入时间);`arrived_at_ms` 每次覆盖写入(取最后一次到达时刻)。
- **skip 路径显式打点**:`_complete_step_without_verification` 的 has_next_step 分支(session_support.py:155-156)无 refresh 触发,当前 step 的 arrival 必须显式写。
- 时间戳是**设备无关**的 Agent 层证据;`deviceId` 由 Platform 侧 join(spec §6 已定,不在本计划范围)。
- 复用现有:`build_memory_timestamp_ms`、`_activate_step`/`_complete_step`(不改行为、只加时间戳采集)、`ExecutionTraceExporter.export_json` 结构。
- 测试运行:在 `MobiFlow_Agent/` 目录下 `python -m pytest -q`。
- 本计划不动 decide_step/路由/path_guard;不做 Platform join;不做 UI/对话入口。

---

## File Structure

- Modify: `mobiflow_agent/task/session.py` — 加 `waypoint_timings: dict[str, dict[str, int]]`
- Modify: `mobiflow_agent/graph/session_support.py` — Mixin `__init__` 加 `clock` 参数 + `_activate_step`/`_complete_step`/`_complete_step_without_verification` 采集
- Modify: `mobiflow_agent/graph/runtime.py` — `TaskGraphRuntime.__init__` 加 `clock` 参数并透传
- Modify: `mobiflow_agent/runtime/trace_export.py` — `export_json` 挂 `payload["waypoint_segments"]` + 新静态方法 `_build_waypoint_segments`
- Test: `tests/task/test_task_session_waypoint_timings.py`(Create) — TaskSession 字段默认值
- Test: `tests/graph/test_waypoint_timestamp_capture.py`(Create) — clock 注入 + 采集点端到端
- Test: `tests/runtime/test_trace_export_waypoint_segments.py`(Create) — 导出格式

---

## Task 1: TaskSession 加 waypoint_timings 字段

**Files:**
- Modify: `mobiflow_agent/task/session.py`
- Test: `tests/task/test_task_session_waypoint_timings.py`(Create)

**Interfaces:**
- Produces: `TaskSession.waypoint_timings: dict[str, dict[str, int]] = Field(default_factory=dict)`(位置紧邻 `step_summaries`,保持 by-step_id dict 聚簇)。

- [ ] **Step 1: 写失败测试**

Create `tests/task/test_task_session_waypoint_timings.py`:

```python
from mobiflow_agent.task.session import TaskSession


def test_waypoint_timings_defaults_to_empty_dict():
    session = TaskSession(session_id="s1", goal="test")
    assert session.waypoint_timings == {}


def test_waypoint_timings_accepts_by_step_entries():
    session = TaskSession(session_id="s1", goal="test")
    session.waypoint_timings.setdefault("step-a", {})["entered_at_ms"] = 1000
    session.waypoint_timings["step-a"]["arrived_at_ms"] = 2000
    assert session.waypoint_timings["step-a"] == {"entered_at_ms": 1000, "arrived_at_ms": 2000}
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/task/test_task_session_waypoint_timings.py -q`
Expected: FAIL —— `TaskSession` 尚无 `waypoint_timings` 字段(第一个测试 `session.waypoint_timings` AttributeError 或 pydantic model 无此属性)。

- [ ] **Step 3: 加字段**

在 `mobiflow_agent/task/session.py`,`step_summaries: dict[str, StepContextSummary] = Field(default_factory=dict)`(约 :54)**之后**新增一行:

```python
    waypoint_timings: dict[str, dict[str, int]] = Field(default_factory=dict)
```

不改任何 validator。

- [ ] **Step 4: 运行确认通过 + 全量回归**

Run: `python -m pytest tests/task/test_task_session_waypoint_timings.py -q`
Expected: PASS(2 passed)

Run: `python -m pytest -q`
Expected: 全绿(纯新增可选字段,零回归)

- [ ] **Step 5: 提交**

```bash
git add mobiflow_agent/task/session.py tests/task/test_task_session_waypoint_timings.py
git commit -m "feat(task): add waypoint_timings dict to TaskSession"
```

---

## Task 2: clock 注入 + _activate_step/_complete_step 采集时间戳

**Files:**
- Modify: `mobiflow_agent/graph/session_support.py`
- Modify: `mobiflow_agent/graph/runtime.py`
- Test: `tests/graph/test_waypoint_timestamp_capture.py`(Create)

**Interfaces:**
- Consumes: `TaskSession.waypoint_timings`(Task 1)、`build_memory_timestamp_ms`(`memory/store.py:435`)。
- Produces:
  - `TaskGraphSessionSupportMixin.__init__(..., clock: Callable[[], int] = build_memory_timestamp_ms)`(存 `self._clock`)
  - `TaskGraphRuntime.__init__(..., clock=...)`(透传给 super)
  - `_activate_step` 采 `entered_at_ms`(`setdefault` 幂等)
  - `_complete_step` 与 `_complete_step_without_verification` 每条分支都显式采当前 step 的 `arrived_at_ms`

- [ ] **Step 1: 写失败测试**

Create `tests/graph/test_waypoint_timestamp_capture.py`:

```python
from mobiflow_agent.agents.observer import ObserverAgent
from mobiflow_agent.agents.recovery import RecoveryAgent
from mobiflow_agent.agents.step_policy import StepPolicyAgent
from mobiflow_agent.agents.verifier import VerifierAgent
from mobiflow_agent.agents.contracts import StepDecision, StepDecisionType
from mobiflow_agent.common.contracts import (
    EntityKind,
    EvidenceKind,
    EvidenceRef,
    ObservationFact,
    ObservationFactSource,
    ObservationView,
    VerificationCheck,
    VerificationSpec,
)
from mobiflow_agent.graph import TaskGraphRuntime
from mobiflow_agent.waypoint import Waypoint, WaypointSequence


def _arrival_spec(waypoint_id: str) -> VerificationSpec:
    # evidence_hint 用 waypoint_id,与下方 observation 的 value 匹配,让默认 VerifierAgent 判成功
    return VerificationSpec(
        verification_id=f"verification:{waypoint_id}",
        target_kind=EntityKind.TASK,
        target_id=waypoint_id,
        success_checks=[
            VerificationCheck(
                check_id=f"{waypoint_id}-check",
                description="Arrived.",
                evidence_hint=waypoint_id,
            )
        ],
    )


def _observation(observation_id: str, screen_id: str) -> ObservationView:
    return ObservationView(
        observation_id=observation_id,
        focus_kind=EntityKind.TASK,
        focus_id=screen_id,
        facts=[
            ObservationFact(
                fact_id="mobile_observation_summary",
                source=ObservationFactSource.PLATFORM,
                title="Mobile observation summary",
                value={"screen_id": screen_id},
                evidence_refs=[
                    EvidenceRef(
                        evidence_id=f"evidence:{observation_id}",
                        kind=EvidenceKind.PLATFORM_SNAPSHOT,
                        summary=f"Screen {screen_id} observed.",
                        locator=screen_id,
                    )
                ],
            )
        ],
    )


def _sequence() -> WaypointSequence:
    return WaypointSequence(
        sequence_id="capture.v1",
        behavior_label="capture_flow",
        profile_package="com.example.app",
        waypoints=[
            Waypoint(
                waypoint_id="stepA",
                description="Reach stepA.",
                arrival_spec=_arrival_spec("stepA"),
            ),
            Waypoint(
                waypoint_id="stepB",
                description="Reach stepB.",
                arrival_spec=_arrival_spec("stepB"),
            ),
        ],
    )


def test_run_records_entered_and_arrived_timestamps_per_step():
    # 序列化 clock:每次调 +100,便于确定性断言
    ticks = {"n": 0}
    def clock() -> int:
        ticks["n"] += 100
        return ticks["n"]

    observations = iter([_observation("obs-a", "stepA"), _observation("obs-b", "stepB")])

    runtime = TaskGraphRuntime(
        observer_agent=ObserverAgent(observation_provider=lambda _s: next(observations)),
        step_policy_agent=StepPolicyAgent(
            step_policy=lambda _s: StepDecision(
                decision_id="d",
                decision_type=StepDecisionType.STEP_SUCCEEDED,
                summary="Reached.",
            )
        ),
        verifier_agent=VerifierAgent(),
        recovery_agent=RecoveryAgent(),
        clock=clock,
    )
    session = runtime.create_session(
        "capture timing test",
        target_kind=EntityKind.TASK,
        target_id="stepA",
        waypoint_sequence=_sequence(),
    )
    completed = runtime.run(session)

    timings = completed.waypoint_timings
    # 两个 step 都记录了 entered 和 arrived
    assert set(timings.keys()) == {"stepA", "stepB"}
    for step_id in ("stepA", "stepB"):
        entry = timings[step_id]
        assert "entered_at_ms" in entry
        assert "arrived_at_ms" in entry
        # 到达 >= 进入(单调 clock 保证)
        assert entry["arrived_at_ms"] >= entry["entered_at_ms"]
    # stepA 先于 stepB 进入
    assert timings["stepA"]["entered_at_ms"] < timings["stepB"]["entered_at_ms"]


def test_clock_defaults_when_not_injected():
    # 不注入 clock,应回退到 build_memory_timestamp_ms(仍能采到时间戳,只是不可断言精确值)
    observations = iter([_observation("obs-a", "stepA")])
    runtime = TaskGraphRuntime(
        observer_agent=ObserverAgent(observation_provider=lambda _s: next(observations)),
        step_policy_agent=StepPolicyAgent(
            step_policy=lambda _s: StepDecision(
                decision_id="d",
                decision_type=StepDecisionType.STEP_SUCCEEDED,
                summary="Reached.",
            )
        ),
        verifier_agent=VerifierAgent(),
        recovery_agent=RecoveryAgent(),
    )
    seq = WaypointSequence(
        sequence_id="s1",
        behavior_label="b1",
        profile_package="pkg",
        waypoints=[Waypoint(waypoint_id="stepA", description="A.", arrival_spec=_arrival_spec("stepA"))],
    )
    session = runtime.create_session(
        "default clock test",
        target_kind=EntityKind.TASK,
        target_id="stepA",
        waypoint_sequence=seq,
    )
    completed = runtime.run(session)
    entry = completed.waypoint_timings["stepA"]
    assert isinstance(entry["entered_at_ms"], int)
    assert isinstance(entry["arrived_at_ms"], int)
    assert entry["arrived_at_ms"] >= entry["entered_at_ms"]
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/graph/test_waypoint_timestamp_capture.py -q`
Expected: FAIL —— 第一个测试:`TypeError: TaskGraphRuntime.__init__() got an unexpected keyword argument 'clock'`(或若 clock 被吃掉,`timings == {}`)。

- [ ] **Step 3: Mixin 加 clock + 三个方法采集**

在 `mobiflow_agent/graph/session_support.py`:

(a) 顶部 import 区新增:

```python
from typing import Callable
from mobiflow_agent.memory.store import build_memory_timestamp_ms
```
(若 `Callable`/`memory.store` 已 import,合并到现有 import 行。)

(b) `TaskGraphSessionSupportMixin.__init__`(约 :27-43)签名末尾新增 `clock` 参数:

```python
    def __init__(
        self,
        *,
        planner_agent: PlannerAgent | None = None,
        # ... (保留全部现有参数不变) ...
        context_compressor: ContextCompressionService | None = None,
        clock: Callable[[], int] = build_memory_timestamp_ms,
    ):
```

(c) __init__ 方法体末尾(约 :72 之后,与其它 `self._xxx = xxx` 并列)新增:

```python
        self._clock = clock
```

(d) `_activate_step`(:129-137)第 133 行 `session.current_step = ...` **之后**新增一行(采 entered_at,幂等):

```python
        session.waypoint_timings.setdefault(session.current_step.step_id, {}).setdefault("entered_at_ms", self._clock())
```

> `setdefault` 二次是刻意的:外层 `setdefault(step_id, {})` 幂等建 dict,内层 `setdefault("entered_at_ms", ...)` 保证同一 step 若因复活/重试再次 activate,不覆盖第一次真实进入时刻。

(e) `_complete_step`(:139-149)在 `self._refresh_session_context(session)`(:142)**之前**新增(采当前 step 的 arrived_at,允许覆盖以取最后一次到达):

```python
        session.waypoint_timings.setdefault(session.current_step.step_id, {})["arrived_at_ms"] = self._clock()
```

> 注意:两条分支(has_next_step 与终态 COMPLETED)都会经过第 142 行之前,所以只需插一处。has_next_step 分支随后 :145 调 `_activate_step(next_index)` 会给下一 step 采 entered_at——自然形成"当前 arrived → 下一 entered"的时序衔接。

(f) `_complete_step_without_verification`(:151-160):这里 has_next_step 分支(:154-156)**没有 refresh 触发**,skip 路径的当前 step arrival 会漏采。在方法体开头、`if self._has_next_step(session)`(:154)**之前**新增(同款语句):

```python
        session.waypoint_timings.setdefault(session.current_step.step_id, {})["arrived_at_ms"] = self._clock()
```

> 覆盖两条分支(skip → 下一步 / skip → FAILED 终态),都能采到当前 step arrival。

- [ ] **Step 4: runtime.py 透传 clock**

在 `mobiflow_agent/graph/runtime.py`:

(a) 顶部 import 区新增(与既有 typing/memory import 一致):

```python
from typing import Callable
from mobiflow_agent.memory.store import build_memory_timestamp_ms
```

(b) `TaskGraphRuntime.__init__`(:27-44)签名在 `checkpointer` **之前**新增(保持类型顺序自然):

```python
        clock: Callable[[], int] = build_memory_timestamp_ms,
        checkpointer: Any | None = None,
```

(c) `super().__init__(...)`(:45-59)转发列表末尾新增 `clock=clock`:

```python
        super().__init__(
            # ... (保留现有全部转发不变) ...
            context_compressor=context_compressor,
            clock=clock,
        )
```

- [ ] **Step 5: 运行确认通过**

Run: `python -m pytest tests/graph/test_waypoint_timestamp_capture.py -q`
Expected: PASS(2 passed)。若不通过,常见原因:(a) `waypoint_timings` 未在 Task 1 加(检查);(b) `Callable`/`build_memory_timestamp_ms` import 缺失;(c) `_activate_step` 的插入位置在 `session.current_step = ...` **之前**(会 AttributeError);(d) e2e 因 VerifierAgent 判不成功走到 FAILED 而非 COMPLETED,则参照 `tests/graph/test_waypoint_session_integration.py:test_run_executes_injected_waypoint_sequence_skipping_planner` 的现成成功链 helper 调整 arrival_spec/observation,但不放松"两步 timings 齐全 + 单调"这个核心断言。

- [ ] **Step 6: 全量回归**

Run: `python -m pytest -q`
Expected: 全绿。加 clock 参数默认 None-safe(有默认值),现有测试不显式传 clock 也走 `build_memory_timestamp_ms` → `waypoint_timings` 只会被填充,不影响任何现有断言(既有测试不断言 waypoint_timings)。

- [ ] **Step 7: 提交**

```bash
git add mobiflow_agent/graph/session_support.py mobiflow_agent/graph/runtime.py tests/graph/test_waypoint_timestamp_capture.py
git commit -m "feat(graph): inject clock and capture entered/arrived timestamps per waypoint step"
```

---

## Task 3: ExecutionTraceExporter 导出 waypoint_segments

**Files:**
- Modify: `mobiflow_agent/runtime/trace_export.py`
- Test: `tests/runtime/test_trace_export_waypoint_segments.py`(Create)

**Interfaces:**
- Consumes: `TaskSession.plan.behavior_label`(P2-1c)、`TaskSession.plan.steps`、`TaskSession.waypoint_timings`(Task 1)。
- Produces:
  - `ExecutionTraceExporter._build_waypoint_segments(session) -> list[dict]` —— 每条 segment 携带 `{step_id, behavior_label, entered_at_ms, arrived_at_ms, dwell_ms}`,顺序与 `session.plan.steps` 一致。
  - `export_json` 输出的 payload 里新增 `waypoint_segments` 键。

- [ ] **Step 1: 写失败测试**

Create `tests/runtime/test_trace_export_waypoint_segments.py`:

```python
from mobiflow_agent.common.contracts import (
    EntityKind,
    VerificationCheck,
    VerificationSpec,
)
from mobiflow_agent.runtime.trace_export import ExecutionTraceExporter
from mobiflow_agent.task.plan import TaskPlan, TaskStep, TaskStepKind, TaskStepPolicy
from mobiflow_agent.task.session import TaskSession


def _step(step_id: str) -> TaskStep:
    return TaskStep(
        step_id=step_id,
        kind=TaskStepKind.DYNAMIC,
        goal=f"Reach {step_id}.",
        allowed_side_effects=[],
        verification_spec=VerificationSpec(
            verification_id=f"v:{step_id}",
            target_kind=EntityKind.TASK,
            target_id=step_id,
            success_checks=[VerificationCheck(check_id="c", description="d", evidence_hint="e")],
        ),
        policy=TaskStepPolicy(policy_id=f"p:{step_id}", description="."),
    )


def _session_with_timings(behavior_label: str | None) -> TaskSession:
    session = TaskSession(session_id="s1", goal="test")
    session.plan = TaskPlan(
        plan_id="plan-1",
        summary="test plan",
        behavior_label=behavior_label,
        steps=[_step("stepA"), _step("stepB")],
    )
    session.waypoint_timings = {
        "stepA": {"entered_at_ms": 1000, "arrived_at_ms": 1500},
        "stepB": {"entered_at_ms": 1600, "arrived_at_ms": 2500},
    }
    return session


def test_export_json_includes_waypoint_segments_in_plan_order():
    exporter = ExecutionTraceExporter()
    exported = exporter.export_json(_session_with_timings("shopping_checkout"))
    segments = exported["waypoint_segments"]
    assert [seg["step_id"] for seg in segments] == ["stepA", "stepB"]
    assert all(seg["behavior_label"] == "shopping_checkout" for seg in segments)
    assert segments[0]["entered_at_ms"] == 1000
    assert segments[0]["arrived_at_ms"] == 1500
    assert segments[0]["dwell_ms"] == 500
    assert segments[1]["dwell_ms"] == 900


def test_waypoint_segments_omit_step_when_no_timings():
    # 中间 step 没有 timings:该条 segment 的 entered/arrived/dwell 为 None(仍出现,保留位置)
    session = _session_with_timings("b")
    session.waypoint_timings = {"stepA": {"entered_at_ms": 1000, "arrived_at_ms": 1500}}
    exported = ExecutionTraceExporter().export_json(session)
    segments = exported["waypoint_segments"]
    assert len(segments) == 2
    assert segments[1]["step_id"] == "stepB"
    assert segments[1]["entered_at_ms"] is None
    assert segments[1]["arrived_at_ms"] is None
    assert segments[1]["dwell_ms"] is None


def test_waypoint_segments_behavior_label_none_when_missing():
    exported = ExecutionTraceExporter().export_json(_session_with_timings(None))
    assert exported["waypoint_segments"][0]["behavior_label"] is None


def test_waypoint_segments_empty_when_no_plan():
    session = TaskSession(session_id="s1", goal="test")  # 无 plan
    exported = ExecutionTraceExporter().export_json(session)
    assert exported["waypoint_segments"] == []
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/runtime/test_trace_export_waypoint_segments.py -q`
Expected: FAIL —— `exported["waypoint_segments"]` KeyError(export_json 尚未加该键)。

- [ ] **Step 3: 加导出方法**

在 `mobiflow_agent/runtime/trace_export.py` 的 `ExecutionTraceExporter` 类里:

(a) `export_json` 方法(约 :25-69),在 `payload["timeline"] = self._build_timeline(payload)`(约 :68)**之前**新增一行:

```python
        payload["waypoint_segments"] = self._build_waypoint_segments(session)
```

(b) 在类内新增静态方法(建议放在 `_build_timeline` 附近,保持 build 系列聚合):

```python
    @staticmethod
    def _build_waypoint_segments(session: TaskSession) -> list[dict[str, Any]]:
        if session.plan is None:
            return []
        behavior_label = session.plan.behavior_label
        segments: list[dict[str, Any]] = []
        for step in session.plan.steps:
            timing = session.waypoint_timings.get(step.step_id, {})
            entered_at_ms = timing.get("entered_at_ms")
            arrived_at_ms = timing.get("arrived_at_ms")
            dwell_ms = (
                arrived_at_ms - entered_at_ms
                if entered_at_ms is not None and arrived_at_ms is not None
                else None
            )
            segments.append(
                {
                    "step_id": step.step_id,
                    "behavior_label": behavior_label,
                    "entered_at_ms": entered_at_ms,
                    "arrived_at_ms": arrived_at_ms,
                    "dwell_ms": dwell_ms,
                }
            )
        return segments
```

> 注意:如需 `TaskSession` 类型注解,顶部 import 若已有 `from mobiflow_agent.task.session import TaskSession` 保留即可;若无则新增(该文件应已引用 TaskSession)。

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/runtime/test_trace_export_waypoint_segments.py -q`
Expected: PASS(4 passed)

- [ ] **Step 5: 全量回归**

Run: `python -m pytest -q`
Expected: 全绿。新增 payload 键对已有 test_trace_export 测试透明——它们只断言各自关心的字段,不做全键集断言(已核实)。

- [ ] **Step 6: 提交**

```bash
git add mobiflow_agent/runtime/trace_export.py tests/runtime/test_trace_export_waypoint_segments.py
git commit -m "feat(runtime): export device-agnostic waypoint_segments timeline for pcap alignment"
```

---

## Task 4: 端到端 —— run 后 waypoint_segments 时序确定性

**Files:**
- Modify: `tests/graph/test_waypoint_timestamp_capture.py`(追加)

**Interfaces:**
- Consumes: Task 2 的 clock 注入 + 采集、Task 3 的导出。
- Produces: 端到端断言:注入序列化 clock 化 run 后,`ExecutionTraceExporter.export_json(session)["waypoint_segments"]` 时序确定、含 behavior_label、单调递增。

- [ ] **Step 1: 追加端到端测试**

在 Task 2 建的 `tests/graph/test_waypoint_timestamp_capture.py` 末尾追加:

```python
from mobiflow_agent.runtime.trace_export import ExecutionTraceExporter


def test_e2e_waypoint_segments_deterministic_under_injected_clock():
    ticks = {"n": 0}
    def clock() -> int:
        ticks["n"] += 100
        return ticks["n"]

    observations = iter([_observation("obs-a", "stepA"), _observation("obs-b", "stepB")])

    runtime = TaskGraphRuntime(
        observer_agent=ObserverAgent(observation_provider=lambda _s: next(observations)),
        step_policy_agent=StepPolicyAgent(
            step_policy=lambda _s: StepDecision(
                decision_id="d",
                decision_type=StepDecisionType.STEP_SUCCEEDED,
                summary="Reached.",
            )
        ),
        verifier_agent=VerifierAgent(),
        recovery_agent=RecoveryAgent(),
        clock=clock,
    )
    session = runtime.create_session(
        "e2e timeline",
        target_kind=EntityKind.TASK,
        target_id="stepA",
        waypoint_sequence=_sequence(),
    )
    completed = runtime.run(session)

    exported = ExecutionTraceExporter().export_json(completed)
    segments = exported["waypoint_segments"]

    # 顺序按 plan 顺序
    assert [seg["step_id"] for seg in segments] == ["stepA", "stepB"]
    # behavior_label 从 plan 透出
    assert all(seg["behavior_label"] == "capture_flow" for seg in segments)
    # 每条都有完整时间戳
    for seg in segments:
        assert isinstance(seg["entered_at_ms"], int)
        assert isinstance(seg["arrived_at_ms"], int)
        assert seg["dwell_ms"] == seg["arrived_at_ms"] - seg["entered_at_ms"]
        assert seg["dwell_ms"] >= 0
    # stepA 完整早于 stepB
    assert segments[0]["arrived_at_ms"] <= segments[1]["entered_at_ms"]
```

- [ ] **Step 2: 运行确认通过**

Run: `python -m pytest tests/graph/test_waypoint_timestamp_capture.py -q`
Expected: PASS(3 passed:含 Task 2 的 2 个 + 新 e2e 1 个)

- [ ] **Step 3: 全量回归**

Run: `python -m pytest -q`
Expected: 全绿,无回归。

- [ ] **Step 4: 提交**

```bash
git add tests/graph/test_waypoint_timestamp_capture.py
git commit -m "test(graph): e2e — waypoint_segments deterministic under injected clock"
```

---

## 后续计划(不在本计划范围)

- **P2-2**:Platform(Java)异构分派 + join deviceId 到 waypoint_segments(设备无关时间线 + Platform 侧的 deviceId 拼接产出可与 pcap 对齐的完整证据链)。
- **P2-3**:对话入口(IntentPlanner/DispatchPlan)+ UI 前端。
