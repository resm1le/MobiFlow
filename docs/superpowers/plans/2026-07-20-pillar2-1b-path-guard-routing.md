# P2-1b 路径约束守卫与终态失败路由 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让航点的 `path_constraint` 数据流入执行闭环,并新增 `PathConstraintGuard`——动态步决策提出执行动作时,若当前屏幕越出 `required_screens` 或动作命中 `forbidden_actions`,判定为不可恢复的终态失败(`off_standard_path`),不进 recover 硬凑;守护"宁缺毋滥、不产脏样本"。

**Architecture:** 分四步。(1) 给 `TaskStep` 加可选字段 `path_constraint`(向后兼容,现有 step 不设即 None)。(2) 编译器把 `Waypoint.path_constraint` 写入编译出的 step,并调整 P2-1a 那条"编译丢弃 path_constraint"的测试(改为断言写入,同时仍丢弃 strength/rendezvous)。(3) 新增纯函数 `evaluate_path_constraint(current_step, observation, proposal) -> str | None`,返回违规原因或 None。(4) 在 `decide_step` 的 PROPOSE_EXECUTION 分支、allowlist 通过后接入 guard,越界则走 `off_standard_path` 终态失败(transition FAILED + completion_verdict FAILED,route_hint=`writeback_memory`),并在 builder 的 decide_step 条件边补 `writeback_memory` 目标键。

**Tech Stack:** Python 3.11+、pydantic v2(`StrictModel`)、LangGraph、pytest。

## Global Constraints

- 新代码遵循现有惯例:读 `mobile_observation_summary` fact 时**硬编码字符串字面量 `"mobile_observation_summary"`**(与 `step_policy.py:256`、`verifier.py`、`memory/runtime.py` 一致),不 import simulation 层常量,避免 graph 层依赖 simulation 层。
- `off_standard_path` 终态失败走 **writeback_memory**(与现有 `_route_replan_decision` 的 FAIL 分支模式一致:先 `ops._transition(session, TaskStatus.FAILED)` + `session.completion_verdict = TaskCompletionVerdict.FAILED`,再 route 到 writeback_memory)。不走 finalize。
- 测试运行:在 `MobiFlow_Agent/` 目录下 `python -m pytest -q`。
- `fact.value` 是 **dict**(不是 pydantic 对象),`screen_id` 是键:访问用 `fact.value.get("screen_id")`,并加 `isinstance(fact.value, dict)` 守卫。
- guard 是**纯函数**,不碰 session/ops、无副作用,只读三个入参返回 `str | None`,以便独立单测。
- 复用现有构件:`PathConstraint`(`waypoint/models.py`)、`ObservationView`/`ObservationFact`(`common/contracts.py`)、`ExecutionProposal`(`common/contracts.py`)、`TaskStep`(`task/plan.py`)、`_dynamic_blocked_verdict` 不复用(它构造的是会走 recover 的 BLOCKED verdict;终态失败另写)。
- 本计划不做航点段时间线(拆到 P2-1c);不加时间戳采集;不碰 Platform/Java。

---

## File Structure

- Modify: `mobiflow_agent/task/plan.py` — `TaskStep` 加 `path_constraint: PathConstraint | None = None`(需 import `PathConstraint`)
- Modify: `mobiflow_agent/waypoint/compiler.py` — `_compile_step` 写入 `path_constraint=waypoint.path_constraint`
- Modify: `tests/waypoint/test_waypoint_compiler.py` — 调整 `test_compiled_step_does_not_carry_waypoint_only_fields`
- Create: `mobiflow_agent/graph/path_guard.py` — 纯函数 `evaluate_path_constraint`
- Create: `tests/graph/test_path_guard.py` — guard 单元测试
- Modify: `mobiflow_agent/graph/nodes.py` — decide_step PROPOSE_EXECUTION 分支接入 guard + 新增 `_off_standard_path_failure` 辅助
- Modify: `mobiflow_agent/graph/builder.py` — decide_step 条件边补 `writeback_memory` 目标
- Modify: `tests/graph/test_task_graph_runtime.py` — 端到端:越界触发 off_standard_path 终态失败

> 潜在循环 import 注意:`task/plan.py` import `waypoint/models.py` 的 `PathConstraint`。确认 `waypoint/models.py` 不 import `task/plan.py`(它只 import `common.contracts`),故无环。Task 1 首步须验证 import 成功。

---

## Task 1: TaskStep 增加 path_constraint 字段

**Files:**
- Modify: `mobiflow_agent/task/plan.py`
- Test: `tests/task/test_task_step_path_constraint.py`(Create)

**Interfaces:**
- Consumes: `PathConstraint`——**本任务先把它从 `waypoint/models.py` 迁到 `common/contracts.py`**(破环,见 Step 3),`waypoint.models` 保留 re-export。
- Produces: `TaskStep.path_constraint: PathConstraint | None = None`(可选,默认 None,向后兼容);`common.contracts.PathConstraint` 成为该数据类的规范定义位置。

- [ ] **Step 1: 写失败测试**

Create `tests/task/test_task_step_path_constraint.py`:

```python
from mobiflow_agent.common.contracts import EntityKind
from mobiflow_agent.task.plan import TaskStep, TaskStepKind, TaskStepPolicy
from mobiflow_agent.waypoint.models import PathConstraint


def _policy() -> TaskStepPolicy:
    return TaskStepPolicy(policy_id="policy:x", description="Bounded actions.")


def test_task_step_path_constraint_defaults_to_none():
    step = TaskStep(
        step_id="s1",
        kind=TaskStepKind.DYNAMIC,
        goal="Reach x.",
        policy=_policy(),
    )
    assert step.path_constraint is None


def test_task_step_accepts_path_constraint():
    step = TaskStep(
        step_id="s1",
        kind=TaskStepKind.DYNAMIC,
        goal="Reach x.",
        policy=_policy(),
        path_constraint=PathConstraint(
            required_screens=["chat"],
            forbidden_actions=["search"],
        ),
    )
    assert step.path_constraint.required_screens == ["chat"]
    assert step.path_constraint.forbidden_actions == ["search"]
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/task/test_task_step_path_constraint.py -q`
Expected: FAIL —— `TypeError`/`ValidationError`：`TaskStep` 尚无 `path_constraint`（extra="forbid" 会拒绝该关键字）。

- [ ] **Step 3: 先修循环 import —— 把 PathConstraint 迁到 common/contracts.py**

> **成因(计划修订):** `task/plan.py` 若直接 `from mobiflow_agent.waypoint.models import PathConstraint`,会先执行 `waypoint/__init__.py`,后者 re-export 了 `compiler`,而 `compiler` import 了 `task/plan` → 成环。解法(经负责人拍板):把纯数据类 `PathConstraint`(仅依赖 `StrictModel`)迁到 `common/contracts.py` 共享契约层,`waypoint/models.py` 改为从 common import 并 re-export(保持 `from mobiflow_agent.waypoint import PathConstraint` 等现有 API 不变)。

(a) 在 `mobiflow_agent/common/contracts.py` 中,`StrictModel` 定义之后的合适位置(与其它 StrictModel 子类并列,例如紧邻 `VerificationCheck` 之前或文件里其它数据模型附近)新增:

```python
class PathConstraint(StrictModel):
    required_screens: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)
```

(b) 编辑 `mobiflow_agent/waypoint/models.py`:删除原本定义的 `PathConstraint` 类(第 17-19 行那三行 class 定义),改为从 common import 并保留可被 re-export 的名字。把第 9 行的
```python
from mobiflow_agent.common.contracts import StrictModel, VerificationSpec
```
改为:
```python
from mobiflow_agent.common.contracts import PathConstraint, StrictModel, VerificationSpec
```
`Waypoint.path_constraint: PathConstraint | None = None` 引用不变(现在指向 common 的同名类)。`waypoint/__init__.py` 对 `PathConstraint` 的 re-export 不变(仍从 `models` 拿,models 已 re-export)。

(c) 验证迁移未破坏 P2-1a:
Run: `python -m pytest tests/waypoint/ -q`
Expected: PASS(P2-1a 全部用例仍绿——`from mobiflow_agent.waypoint import PathConstraint` 与 `from ...waypoint.models import PathConstraint` 都仍可用)。

- [ ] **Step 4: 改 plan.py 加字段**

在 `mobiflow_agent/task/plan.py` 顶部 import 区,`PathConstraint` 现在从 common 拿(无环)。若文件已 `from mobiflow_agent.common.contracts import ...`,把 `PathConstraint` 加进该 import 列表;否则新增一行:

```python
from mobiflow_agent.common.contracts import PathConstraint
```

在 `TaskStep` 类里,`verification_spec: VerificationSpec | None = None` 之后新增一行:

```python
    path_constraint: PathConstraint | None = None
```

- [ ] **Step 5: 运行确认通过 + 无循环 import**

Run: `python -m pytest tests/task/test_task_step_path_constraint.py -q`
Expected: PASS(2 passed)

Run: `python -c "import mobiflow_agent.task.plan; import mobiflow_agent.waypoint"`
Expected: 无输出、无异常(不再有 ImportError)。

- [ ] **Step 6: 全量回归 + 提交**

Run: `python -m pytest -q`
Expected: 全绿(P2-1a + 新增均通过,无回归)

```bash
git add mobiflow_agent/common/contracts.py mobiflow_agent/waypoint/models.py mobiflow_agent/task/plan.py tests/task/test_task_step_path_constraint.py
git commit -m "feat(task): add optional path_constraint to TaskStep; move PathConstraint to common to break import cycle"
```

---

## Task 2: 编译器写入 path_constraint

**Files:**
- Modify: `mobiflow_agent/waypoint/compiler.py`
- Modify: `tests/waypoint/test_waypoint_compiler.py`

**Interfaces:**
- Consumes: `Waypoint.path_constraint`(Task 1 已让 `TaskStep` 能承载)。
- Produces: `_compile_step` 产出的 `TaskStep` 携带 `path_constraint=waypoint.path_constraint`(waypoint 未设则为 None);`strength`/`rendezvous` 仍不进 step。

- [ ] **Step 1: 改现有丢弃测试 + 加写入测试(先让其失败)**

在 `tests/waypoint/test_waypoint_compiler.py`：

(a) 现有 helper `_sequence()` 的第一个 waypoint 目前不带 path_constraint。新增一个带约束的 helper 用于本任务测试（不改 `_sequence()`，避免影响其它测试）：

```python
from mobiflow_agent.waypoint import PathConstraint, WaypointStrength


def _sequence_with_constraint() -> WaypointSequence:
    return WaypointSequence(
        sequence_id="wechat.video_call.v1",
        behavior_label="wechat_video_call",
        profile_package="com.tencent.mm",
        waypoints=[
            Waypoint(
                waypoint_id="call_connected",
                description="Reach connected call.",
                arrival_spec=_arrival_spec("call_connected"),
                strength=WaypointStrength.STRICT,
                path_constraint=PathConstraint(
                    required_screens=["chat", "call_dialog"],
                    forbidden_actions=["search"],
                ),
            )
        ],
    )
```

(b) 把现有测试 `test_compiled_step_does_not_carry_waypoint_only_fields` 中对 `path_constraint` 的断言**移除**（因为现在 path_constraint 会被写入 step），只保留 strength/rendezvous 仍被丢弃。改为：

```python
def test_compiled_step_does_not_carry_strength_or_rendezvous():
    plan = compile_sequence_to_plan(_sequence())
    step = plan.steps[0]
    for field_name in ("strength", "rendezvous"):
        assert not hasattr(step, field_name)
```

（把原函数名 `test_compiled_step_does_not_carry_waypoint_only_fields` 整体替换为上面这个新函数。）

(c) 新增写入测试：

```python
def test_compiler_writes_path_constraint_into_step():
    plan = compile_sequence_to_plan(_sequence_with_constraint())
    step = plan.steps[0]
    assert step.path_constraint is not None
    assert step.path_constraint.required_screens == ["chat", "call_dialog"]
    assert step.path_constraint.forbidden_actions == ["search"]


def test_compiler_leaves_path_constraint_none_when_absent():
    plan = compile_sequence_to_plan(_sequence())  # _sequence 的 waypoints 无 path_constraint
    assert plan.steps[0].path_constraint is None
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/waypoint/test_waypoint_compiler.py -q`
Expected: FAIL —— `test_compiler_writes_path_constraint_into_step` 失败（当前 `_compile_step` 未写入，`step.path_constraint` 为 None）。

- [ ] **Step 3: 改编译器**

在 `mobiflow_agent/waypoint/compiler.py` 的 `_compile_step` 里,给 `TaskStep(...)` 构造新增一个参数 `path_constraint=waypoint.path_constraint`:

```python
def _compile_step(waypoint: Waypoint) -> TaskStep:
    return TaskStep(
        step_id=waypoint.waypoint_id,
        kind=TaskStepKind.DYNAMIC,
        goal=waypoint.description,
        allowed_side_effects=[],
        verification_spec=waypoint.arrival_spec,
        path_constraint=waypoint.path_constraint,
        policy=TaskStepPolicy(
            policy_id=f"policy:{waypoint.waypoint_id}",
            description=f"Bounded actions to reach waypoint {waypoint.waypoint_id}.",
            max_iterations=3,
        ),
    )
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/waypoint/test_waypoint_compiler.py -q`
Expected: PASS（原有测试数 - 1 删除 + 2 新增，全绿）

- [ ] **Step 5: 提交**

```bash
git add mobiflow_agent/waypoint/compiler.py tests/waypoint/test_waypoint_compiler.py
git commit -m "feat(waypoint): compile path_constraint into TaskStep; adjust drop-field test"
```

---

## Task 3: PathConstraintGuard 纯函数

**Files:**
- Create: `mobiflow_agent/graph/path_guard.py`
- Test: `tests/graph/test_path_guard.py`(Create)

**Interfaces:**
- Consumes: `TaskStep`（`task/plan.py`）、`ObservationView`（`common/contracts.py`）、`ExecutionProposal`（`common/contracts.py`）、`PathConstraint`（`waypoint/models.py`）。
- Produces:
  - `OFF_STANDARD_PATH = "off_standard_path"`（模块级常量）
  - `def evaluate_path_constraint(step: TaskStep, observation: ObservationView | None, proposal: ExecutionProposal) -> str | None`
    - step 无 `path_constraint` → 返回 None（不约束）
    - `forbidden_actions` 非空且 `proposal.action_tool_name` 命中 → 返回违规原因字符串
    - `required_screens` 非空:从 observation 的 `mobile_observation_summary` fact 取 `screen_id`;若当前 screen_id 不在 required_screens → 返回违规原因;observation 为 None 或取不到 screen_id 时也视为越界（无法证明在标准屏）→ 返回违规原因
    - 全部通过 → 返回 None

- [ ] **Step 1: 写失败测试**

Create `tests/graph/test_path_guard.py`:

```python
from mobiflow_agent.common.contracts import (
    EntityKind,
    ExecutionProposal,
    ObservationFact,
    ObservationFactSource,
    ObservationView,
)
from mobiflow_agent.task.plan import TaskStep, TaskStepKind, TaskStepPolicy
from mobiflow_agent.waypoint.models import PathConstraint
from mobiflow_agent.graph.path_guard import (
    OFF_STANDARD_PATH,
    evaluate_path_constraint,
)


def _step(path_constraint: PathConstraint | None) -> TaskStep:
    return TaskStep(
        step_id="s1",
        kind=TaskStepKind.DYNAMIC,
        goal="Reach x.",
        allowed_side_effects=["tap_element"],
        path_constraint=path_constraint,
        policy=TaskStepPolicy(policy_id="policy:x", description="Bounded."),
    )


def _proposal(action: str) -> ExecutionProposal:
    return ExecutionProposal(
        proposal_id="p1",
        action_tool_name=action,
        arguments={"element": "ok"},
        rationale="advance",
    )


def _observation(screen_id: str | None) -> ObservationView:
    value = {"screen_id": screen_id} if screen_id is not None else {}
    return ObservationView(
        observation_id="obs-1",
        focus_kind=EntityKind.TASK,
        focus_id="s1",
        facts=[
            ObservationFact(
                fact_id="mobile_observation_summary",
                source=ObservationFactSource.PLATFORM,
                title="Mobile observation summary",
                value=value,
            )
        ],
    )


def test_no_constraint_returns_none():
    result = evaluate_path_constraint(_step(None), _observation("chat"), _proposal("tap_element"))
    assert result is None


def test_forbidden_action_is_flagged():
    constraint = PathConstraint(forbidden_actions=["search"])
    result = evaluate_path_constraint(_step(constraint), _observation("chat"), _proposal("search"))
    assert result is not None


def test_allowed_action_on_required_screen_passes():
    constraint = PathConstraint(required_screens=["chat"], forbidden_actions=["search"])
    result = evaluate_path_constraint(_step(constraint), _observation("chat"), _proposal("tap_element"))
    assert result is None


def test_wrong_screen_is_flagged():
    constraint = PathConstraint(required_screens=["chat"])
    result = evaluate_path_constraint(_step(constraint), _observation("moments"), _proposal("tap_element"))
    assert result is not None


def test_missing_screen_id_is_flagged_when_required_screens_set():
    constraint = PathConstraint(required_screens=["chat"])
    result = evaluate_path_constraint(_step(constraint), _observation(None), _proposal("tap_element"))
    assert result is not None


def test_none_observation_is_flagged_when_required_screens_set():
    constraint = PathConstraint(required_screens=["chat"])
    result = evaluate_path_constraint(_step(constraint), None, _proposal("tap_element"))
    assert result is not None


def test_empty_constraint_lists_pass():
    constraint = PathConstraint()  # 两个列表都空
    result = evaluate_path_constraint(_step(constraint), _observation("anything"), _proposal("tap_element"))
    assert result is None
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/graph/test_path_guard.py -q`
Expected: FAIL —— `ModuleNotFoundError: No module named 'mobiflow_agent.graph.path_guard'`

- [ ] **Step 3: 写 guard 实现**

Create `mobiflow_agent/graph/path_guard.py`:

```python
"""路径约束守卫:判定动态步提出的动作是否偏离标准路径。

纯函数,无副作用。数据源与现有惯例一致:当前屏幕取自
`mobile_observation_summary` 观察事实的 `screen_id`(硬编码字面量,
与 step_policy.py/verifier.py 一致,避免 graph 层依赖 simulation 层)。
"""

from __future__ import annotations

from mobiflow_agent.common.contracts import ExecutionProposal, ObservationView
from mobiflow_agent.task.plan import TaskStep

OFF_STANDARD_PATH = "off_standard_path"

_MOBILE_OBSERVATION_SUMMARY_FACT_ID = "mobile_observation_summary"


def _current_screen_id(observation: ObservationView | None) -> str | None:
    if observation is None:
        return None
    for fact in observation.facts:
        if fact.fact_id == _MOBILE_OBSERVATION_SUMMARY_FACT_ID and isinstance(fact.value, dict):
            return fact.value.get("screen_id")
    return None


def evaluate_path_constraint(
    step: TaskStep,
    observation: ObservationView | None,
    proposal: ExecutionProposal,
) -> str | None:
    """返回违规原因字符串(越界),或 None(符合标准路径 / 无约束)。"""
    constraint = step.path_constraint
    if constraint is None:
        return None

    if constraint.forbidden_actions and proposal.action_tool_name in constraint.forbidden_actions:
        return (
            f"Proposed action '{proposal.action_tool_name}' is forbidden by the "
            f"path constraint for waypoint '{step.step_id}'."
        )

    if constraint.required_screens:
        screen_id = _current_screen_id(observation)
        if screen_id is None:
            return (
                f"Cannot confirm the current screen for waypoint '{step.step_id}'; "
                f"required one of {constraint.required_screens}."
            )
        if screen_id not in constraint.required_screens:
            return (
                f"Current screen '{screen_id}' is outside the standard path for "
                f"waypoint '{step.step_id}' (required one of {constraint.required_screens})."
            )

    return None
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/graph/test_path_guard.py -q`
Expected: PASS(7 passed)

- [ ] **Step 5: 提交**

```bash
git add mobiflow_agent/graph/path_guard.py tests/graph/test_path_guard.py
git commit -m "feat(graph): add pure PathConstraintGuard evaluating screen and action"
```

---

## Task 4: 在 decide_step 接入 guard + 终态失败路由

**Files:**
- Modify: `mobiflow_agent/graph/nodes.py`
- Modify: `mobiflow_agent/graph/builder.py`
- Test: `tests/graph/test_task_graph_runtime.py`(新增端到端测试)

**Interfaces:**
- Consumes: `evaluate_path_constraint`/`OFF_STANDARD_PATH`（Task 3）；decide_step 的 PROPOSE_EXECUTION 分支（`nodes.py:143-154`）；`_step_routes()`（`builder.py:136`）；`TaskStatus.FAILED`、`TaskCompletionVerdict.FAILED`。
- Produces: PROPOSE_EXECUTION 分支中，allowlist 通过后追加 path 检查；越界时 session transition 到 FAILED、`completion_verdict=FAILED`、`route_hint="writeback_memory"`；builder 的 decide_step 条件边新增 `"writeback_memory": "writeback_memory"` 目标。

- [ ] **Step 1: 写端到端失败测试**

在 `tests/graph/test_task_graph_runtime.py` 末尾新增。它构造一个带 `path_constraint`（forbidden_actions 含提议动作）的 plan，step_policy 提议该被禁动作，断言任务以 FAILED 终态收场且未执行动作、且失败原因是 off_standard_path。

参照文件顶部现有 helper（`_proposal`、`_step_decision`、`_verification_spec`、`_build_observation`），并需手工塞 plan（模式见文件中 `test_task_graph_runtime_dynamic_recovery_replan_skip_without_next_step_fails_unknown` 对 `session.plan`/`session.contract` 的构造）。

```python
def test_task_graph_runtime_off_standard_path_fails_without_recovery() -> None:
    # 当前屏 = "moments"，required_screens 只允许 "chat"，且 forbidden_actions 含 "post_moment"
    from mobiflow_agent.waypoint.models import PathConstraint
    from mobiflow_agent.graph.path_guard import OFF_STANDARD_PATH

    def observe(_session):
        return ObservationView(
            observation_id="obs-1",
            focus_kind=EntityKind.RUN,
            focus_id="run-123",
            facts=[
                ObservationFact(
                    fact_id="mobile_observation_summary",
                    source=ObservationFactSource.PLATFORM,
                    title="Mobile observation summary",
                    value={"screen_id": "chat"},
                )
            ],
        )

    forbidden_proposal = ExecutionProposal(
        proposal_id="p-forbidden",
        action_tool_name="post_moment",
        arguments={"text": "x"},
        rationale="advance",
    )

    def decide(_session):
        return _step_decision(
            StepDecisionType.PROPOSE_EXECUTION,
            "propose",
            proposal=forbidden_proposal,
        )

    recovery_calls = {"count": 0}

    def recover(session, failure_verdict):  # 不应被调用
        recovery_calls["count"] += 1
        return RecoveryOutcome(
            summary="should not run",
            replan_decision=ReplanDecision(
                decision_type=ReplanDecisionType.RETRY_CURRENT_STEP,
                summary="noop",
            ),
        )

    runtime = TaskGraphRuntime(
        observer_agent=ObserverAgent(observation_provider=observe),
        step_policy_agent=StepPolicyAgent(step_policy=decide),
        verifier_agent=VerifierAgent(),
        recovery_agent=RecoveryAgent(recovery=recover),
    )

    session = runtime.create_session(
        "Post moment from chat (should be blocked as off standard path)",
        target_kind=EntityKind.RUN,
        target_id="run-123",
        verification_spec=_verification_spec(),
    )
    # 覆盖 plan:单个 DYNAMIC step,带 path_constraint 与 allowlist 允许 post_moment(以便越过 allowlist 检查、命中 path guard)
    session.plan = TaskPlan(
        plan_id="plan:off-path",
        summary="off-path test",
        steps=[
            TaskStep(
                step_id="only_step",
                kind=TaskStepKind.DYNAMIC,
                goal="Do the constrained action.",
                allowed_side_effects=["post_moment"],
                verification_target_kind=EntityKind.RUN,
                verification_target_id="run-123",
                path_constraint=PathConstraint(
                    required_screens=["chat"],
                    forbidden_actions=["post_moment"],
                ),
                policy=TaskStepPolicy(policy_id="policy:only", description="Bounded."),
            )
        ],
    )

    completed = runtime.run(session)

    assert completed.status == TaskStatus.FAILED
    assert completed.completion_verdict == TaskCompletionVerdict.FAILED
    assert completed.last_execution_result is None
    assert recovery_calls["count"] == 0
    assert completed.last_verdict is not None
    assert completed.last_verdict.blocked_reason == OFF_STANDARD_PATH
```

> 说明:step 的 `allowed_side_effects` 特意包含 `post_moment`,让决策**通过** allowlist 检查、从而抵达新的 path guard;guard 再因 `forbidden_actions` 命中而判越界。这样测的是新逻辑而非既有 allowlist。

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/graph/test_task_graph_runtime.py::test_task_graph_runtime_off_standard_path_fails_without_recovery -q`
Expected: FAIL —— 当前无 guard,决策会走 `dynamic_execute` 执行动作,任务不会以 off_standard_path 失败（可能 recovery_calls>0 或 status 非 FAILED，或 blocked_reason 不等于 off_standard_path）。

- [ ] **Step 3: 在 nodes.py 接入 guard**

在 `mobiflow_agent/graph/nodes.py` 顶部 import 区新增:

```python
from mobiflow_agent.graph.path_guard import OFF_STANDARD_PATH, evaluate_path_constraint
```

在 `decide_step` 的 PROPOSE_EXECUTION 分支里（`nodes.py:143-154`），把现有 `else`（allowlist 通过）分支改为：allowlist 通过后先跑 path guard，越界则终态失败。将：

```python
        else:
            next_role = AgentRole.EXECUTOR
            route_hint = "dynamic_execute"
```

替换为：

```python
        else:
            path_violation = evaluate_path_constraint(
                session.current_step, session.last_observation, decision.proposal
            )
            if path_violation is not None:
                return _off_standard_path_failure(session, ops, path_violation)
            next_role = AgentRole.EXECUTOR
            route_hint = "dynamic_execute"
```

然后在 `_dynamic_blocked_verdict`（`nodes.py:383` 附近）旁新增终态失败辅助函数（放在 `_dynamic_blocked_verdict` 定义之后）：

```python
def _off_standard_path_failure(session: TaskSession, ops: TaskGraphOps, reason: str) -> dict:
    session.last_verdict = _dynamic_blocked_verdict(
        session,
        blocked_reason=OFF_STANDARD_PATH,
        summary=reason,
    )
    ops._transition(session, TaskStatus.FAILED)
    session.completion_verdict = TaskCompletionVerdict.FAILED
    ops._refresh_session_context(session)
    return {"session": session, "route_hint": "writeback_memory", "last_error": OFF_STANDARD_PATH}
```

> 说明:复用 `_dynamic_blocked_verdict` 仅用于构造带 `blocked_reason=off_standard_path` 的 verdict 记录（它构造的 verdict.status=BLOCKED，用于留证）；随后立即 `_transition(FAILED)` + `completion_verdict=FAILED` + 路由 `writeback_memory`——这条路径不经过 recover，与 replan FAIL 分支的终态模式一致。

- [ ] **Step 4: 在 builder.py 补 decide_step 边目标**

`decide_step` 的条件边当前用 `_step_routes()`（不含 `writeback_memory`）。改为显式补上该目标。在 `mobiflow_agent/graph/builder.py` 中 `decide_step` 的 `add_conditional_edges`（第 71-75 附近）里，把路由映射从 `_step_routes()` 改为 `{**_step_routes(), "writeback_memory": "writeback_memory"}`：

找到形如：

```python
    graph.add_conditional_edges(
        "decide_step",
        route_after_decide_step,
        _step_routes(),
    )
```

改为：

```python
    graph.add_conditional_edges(
        "decide_step",
        route_after_decide_step,
        {**_step_routes(), "writeback_memory": "writeback_memory"},
    )
```

> `_normalize_route` 已放行 `writeback_memory`（routes.py:56-57），无需改 routes.py。

- [ ] **Step 5: 运行端到端测试确认通过**

Run: `python -m pytest tests/graph/test_task_graph_runtime.py::test_task_graph_runtime_off_standard_path_fails_without_recovery -q`
Expected: PASS

- [ ] **Step 6: 全量回归**

Run: `python -m pytest -q`
Expected: 全绿。特别确认既有 decide_step / recover / dynamic_execute 相关测试未回归（guard 只在 PROPOSE_EXECUTION 且 step 有 path_constraint 时介入；现有测试的 step 无 path_constraint，guard 返回 None，行为不变）。

- [ ] **Step 7: 提交**

```bash
git add mobiflow_agent/graph/nodes.py mobiflow_agent/graph/builder.py tests/graph/test_task_graph_runtime.py
git commit -m "feat(graph): enforce path constraint in decide_step with off_standard_path terminal failure"
```

---

## 后续计划(不在本计划范围)

- **P2-1c**:航点段时间线导出。需先补步骤级时间戳采集（session 当前无任何时间戳字段），再在 `trace_export.py` 新增设备无关的航点段时间线（`waypoint_id`/`behavior_label`/进入-到达时间戳/verdict）；`behavior_label` 需编译期另存（当前仅在 `plan.summary` 文本里）。
- **P2-2**:Platform(Java)异构分派。
- **P2-3**:对话入口 + Platform join deviceId 到航点时间线。
