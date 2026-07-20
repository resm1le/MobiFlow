# P2-1a 航点序列模型与编译器 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 MobiFlow_Agent 新增"语义航点序列"数据模型,并提供把一条航点序列编译成可被现有 `TaskGraphRuntime` 执行的 `TaskPlan` 的纯函数编译器。

**Architecture:** 纯新增子模块 `mobiflow_agent/waypoint/`,不改动任何现有闭环/图路由。航点的"到达校验" `arrival_spec` 直接复用现有 `VerificationSpec`;编译器把每个航点映射为一个 `DYNAMIC` `TaskStep`(自带 `TaskStepPolicy` + `verification_spec`),`step_id = waypoint_id`,以便后续时间线按 step_id 对回航点。`PathConstraint`/`rendezvous` 仅作为数据字段落地,其判定/编排逻辑不在本计划(留给 P2-1b / 支柱三)。

**Tech Stack:** Python 3.11+、pydantic v2(`StrictModel` = `BaseModel` + `ConfigDict(extra="forbid")`)、pytest。

## Global Constraints

- 所有新模型继承 `mobiflow_agent.common.contracts.StrictModel`(即 `extra="forbid"`,多余字段报错)。逐字复制该约定。
- 测试运行器:在 `MobiFlow_Agent/` 目录下 `python -m pytest -q`。
- 复用现有构件,不得重造:`VerificationSpec`/`VerificationCheck`/`VerificationPredicate`(`common/contracts.py`)、`TaskPlan`/`TaskStep`/`TaskStepKind`/`TaskStepPolicy`(`task/plan.py`)、`build_task_plan_id`(`common/ids.py`)、`EntityKind`(`common/contracts.py`)。
- `VerificationSpec` 的 validator 要求 `success_checks` 至少 1 条——航点的 `arrival_spec` 天然继承此约束。
- `TaskStep` 的 validator:`kind==DYNAMIC` 时 `policy` 必须非空;若设 `proposal` 则其 `action_tool_name` 必须在 `allowed_side_effects` 内。编译器产出的 step 不设 `proposal`(留空),故只需保证 `policy` 非空。
- 本计划不改现有闭环、不改图、不改 `create_session`、不动 `common/contracts.py` 与 `task/plan.py`(只读复用)。

---

## File Structure

- Create: `mobiflow_agent/waypoint/__init__.py` — 子模块导出面
- Create: `mobiflow_agent/waypoint/models.py` — `WaypointStrength`、`PathConstraint`、`RendezvousSpec`、`Waypoint`、`WaypointSequence`
- Create: `mobiflow_agent/waypoint/compiler.py` — `compile_sequence_to_plan(sequence) -> TaskPlan`
- Create: `tests/waypoint/__init__.py` — 空包标记
- Create: `tests/waypoint/test_waypoint_models.py` — 模型不变量测试
- Create: `tests/waypoint/test_waypoint_compiler.py` — 编译器测试

---

## Task 1: 航点序列数据模型

**Files:**
- Create: `mobiflow_agent/waypoint/models.py`
- Test: `tests/waypoint/test_waypoint_models.py`
- Create: `tests/waypoint/__init__.py`

**Interfaces:**
- Consumes: `StrictModel`、`VerificationSpec`、`EntityKind`、`VerificationCheck`、`VerificationPredicate`、`VerificationPredicateOperator`(均来自 `mobiflow_agent.common.contracts`)。
- Produces:
  - `class WaypointStrength(str, Enum)`: `COMMONSENSE="commonsense"`, `STRICT="strict"`
  - `class PathConstraint(StrictModel)`: `required_screens: list[str]=[]`, `forbidden_actions: list[str]=[]`
  - `class RendezvousSpec(StrictModel)`: `barrier_id: str(min_length=1)`, `role: str(min_length=1)`
  - `class Waypoint(StrictModel)`: `waypoint_id: str(min_length=1)`, `description: str(min_length=1)`, `arrival_spec: VerificationSpec`, `strength: WaypointStrength=COMMONSENSE`, `path_constraint: PathConstraint|None=None`, `rendezvous: RendezvousSpec|None=None`
  - `class WaypointSequence(StrictModel)`: `sequence_id: str(min_length=1)`, `behavior_label: str(min_length=1)`, `profile_package: str(min_length=1)`, `waypoints: list[Waypoint]`(validator:非空 + `waypoint_id` 唯一)

- [ ] **Step 1: 建空测试包并写失败测试**

先创建 `tests/waypoint/__init__.py`(空文件)。

然后写 `tests/waypoint/test_waypoint_models.py`:

```python
import pytest
from pydantic import ValidationError

from mobiflow_agent.common.contracts import (
    EntityKind,
    VerificationCheck,
    VerificationSpec,
)
from mobiflow_agent.waypoint.models import (
    PathConstraint,
    RendezvousSpec,
    Waypoint,
    WaypointSequence,
    WaypointStrength,
)


def _arrival_spec(waypoint_id: str) -> VerificationSpec:
    return VerificationSpec(
        verification_id=f"verification:{waypoint_id}",
        target_kind=EntityKind.TASK,
        target_id=waypoint_id,
        success_checks=[
            VerificationCheck(
                check_id=f"{waypoint_id}-check",
                description="Arrived at waypoint.",
                evidence_hint="Home Screen",
            )
        ],
    )


def _waypoint(waypoint_id: str) -> Waypoint:
    return Waypoint(
        waypoint_id=waypoint_id,
        description=f"Reach {waypoint_id}.",
        arrival_spec=_arrival_spec(waypoint_id),
    )


def test_waypoint_defaults_to_commonsense_and_no_constraint():
    wp = _waypoint("logged_in")
    assert wp.strength == WaypointStrength.COMMONSENSE
    assert wp.path_constraint is None
    assert wp.rendezvous is None


def test_strict_waypoint_carries_path_constraint():
    wp = Waypoint(
        waypoint_id="call_connected",
        description="Reach connected call.",
        arrival_spec=_arrival_spec("call_connected"),
        strength=WaypointStrength.STRICT,
        path_constraint=PathConstraint(
            required_screens=["chat", "call_dialog"],
            forbidden_actions=["search"],
        ),
    )
    assert wp.strength == WaypointStrength.STRICT
    assert wp.path_constraint.required_screens == ["chat", "call_dialog"]


def test_rendezvous_is_optional_and_ignored_field():
    wp = Waypoint(
        waypoint_id="call_started",
        description="Start a call.",
        arrival_spec=_arrival_spec("call_started"),
        rendezvous=RendezvousSpec(barrier_id="call-1", role="caller"),
    )
    assert wp.rendezvous.role == "caller"


def test_sequence_requires_at_least_one_waypoint():
    with pytest.raises(ValidationError):
        WaypointSequence(
            sequence_id="wechat.text_chat.v1",
            behavior_label="wechat_text_chat",
            profile_package="com.tencent.mm",
            waypoints=[],
        )


def test_sequence_rejects_duplicate_waypoint_ids():
    with pytest.raises(ValidationError):
        WaypointSequence(
            sequence_id="s1",
            behavior_label="b1",
            profile_package="pkg",
            waypoints=[_waypoint("dup"), _waypoint("dup")],
        )


def test_sequence_extra_field_forbidden():
    with pytest.raises(ValidationError):
        WaypointSequence(
            sequence_id="s1",
            behavior_label="b1",
            profile_package="pkg",
            waypoints=[_waypoint("logged_in")],
            unexpected="x",
        )
```

- [ ] **Step 2: 运行测试,确认失败**

Run: `python -m pytest tests/waypoint/test_waypoint_models.py -q`
Expected: FAIL —— `ModuleNotFoundError: No module named 'mobiflow_agent.waypoint'`

- [ ] **Step 3: 写模型实现**

`mobiflow_agent/waypoint/models.py`:

```python
"""语义航点序列数据模型。一条序列 = 一种行为 = 采集器一个标签。"""

from __future__ import annotations

from enum import Enum

from pydantic import Field, model_validator

from mobiflow_agent.common.contracts import StrictModel, VerificationSpec


class WaypointStrength(str, Enum):
    COMMONSENSE = "commonsense"
    STRICT = "strict"


class PathConstraint(StrictModel):
    required_screens: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)


class RendezvousSpec(StrictModel):
    """支柱三(跨设备协同)预留;本轮调度器忽略此字段。"""

    barrier_id: str = Field(min_length=1)
    role: str = Field(min_length=1)


class Waypoint(StrictModel):
    waypoint_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    arrival_spec: VerificationSpec
    strength: WaypointStrength = WaypointStrength.COMMONSENSE
    path_constraint: PathConstraint | None = None
    rendezvous: RendezvousSpec | None = None


class WaypointSequence(StrictModel):
    sequence_id: str = Field(min_length=1)
    behavior_label: str = Field(min_length=1)
    profile_package: str = Field(min_length=1)
    waypoints: list[Waypoint] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_waypoints(self) -> "WaypointSequence":
        if not self.waypoints:
            raise ValueError("WaypointSequence requires at least one waypoint.")
        ids = [wp.waypoint_id for wp in self.waypoints]
        if len(ids) != len(set(ids)):
            raise ValueError("WaypointSequence waypoint_id values must be unique.")
        return self
```

- [ ] **Step 4: 运行测试,确认通过**

Run: `python -m pytest tests/waypoint/test_waypoint_models.py -q`
Expected: PASS(6 passed)

- [ ] **Step 5: 提交**

```bash
git add mobiflow_agent/waypoint/models.py tests/waypoint/__init__.py tests/waypoint/test_waypoint_models.py
git commit -m "feat(waypoint): add waypoint sequence data model reusing VerificationSpec"
```

---

## Task 2: 航点序列 → TaskPlan 编译器

**Files:**
- Create: `mobiflow_agent/waypoint/compiler.py`
- Create: `mobiflow_agent/waypoint/__init__.py`
- Test: `tests/waypoint/test_waypoint_compiler.py`

**Interfaces:**
- Consumes: `WaypointSequence`/`Waypoint`(Task 1)、`TaskPlan`/`TaskStep`/`TaskStepKind`/`TaskStepPolicy`(`mobiflow_agent.task.plan`)、`build_task_plan_id`(`mobiflow_agent.common.ids`)。
- Produces:
  - `def compile_sequence_to_plan(sequence: WaypointSequence) -> TaskPlan` —— 每个 waypoint 生成一个 `DYNAMIC` `TaskStep`,`step_id == waypoint.waypoint_id`,`goal == waypoint.description`,`verification_spec == waypoint.arrival_spec`,`policy` 为自动生成的 `TaskStepPolicy(policy_id=f"policy:{waypoint_id}", description=..., max_iterations=3)`,`allowed_side_effects` 为空列表。`plan_id` 由 `build_task_plan_id()` 生成,`summary` 由序列信息组成。
  - 子模块 `mobiflow_agent.waypoint` 导出:`WaypointStrength, PathConstraint, RendezvousSpec, Waypoint, WaypointSequence, compile_sequence_to_plan`。

- [ ] **Step 1: 写失败测试**

`tests/waypoint/test_waypoint_compiler.py`:

```python
from mobiflow_agent.common.contracts import (
    EntityKind,
    VerificationCheck,
    VerificationSpec,
)
from mobiflow_agent.task.plan import TaskPlan, TaskStepKind
from mobiflow_agent.waypoint import (
    Waypoint,
    WaypointSequence,
    compile_sequence_to_plan,
)


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


def test_compile_produces_taskplan_with_one_step_per_waypoint():
    plan = compile_sequence_to_plan(_sequence())
    assert isinstance(plan, TaskPlan)
    assert [step.step_id for step in plan.steps] == ["logged_in", "ordered"]


def test_compiled_steps_are_dynamic_with_policy_and_arrival_spec():
    plan = compile_sequence_to_plan(_sequence())
    first = plan.steps[0]
    assert first.kind == TaskStepKind.DYNAMIC
    assert first.policy is not None
    assert first.policy.max_iterations == 3
    assert first.goal == "Reach logged-in state."
    assert first.verification_spec is not None
    assert first.verification_spec.verification_id == "verification:logged_in"


def test_compiled_plan_summary_mentions_behavior_label():
    plan = compile_sequence_to_plan(_sequence())
    assert "shopping_checkout" in plan.summary
```

- [ ] **Step 2: 运行测试,确认失败**

Run: `python -m pytest tests/waypoint/test_waypoint_compiler.py -q`
Expected: FAIL —— `ImportError: cannot import name 'compile_sequence_to_plan'`(以及 `Waypoint`/`WaypointSequence` 尚未在包顶层导出)

- [ ] **Step 3: 写编译器实现**

`mobiflow_agent/waypoint/compiler.py`:

```python
"""把一条航点序列编译成可被 TaskGraphRuntime 执行的 TaskPlan。"""

from __future__ import annotations

from mobiflow_agent.common.ids import build_task_plan_id
from mobiflow_agent.task.plan import (
    TaskPlan,
    TaskStep,
    TaskStepKind,
    TaskStepPolicy,
)
from mobiflow_agent.waypoint.models import Waypoint, WaypointSequence


def _compile_step(waypoint: Waypoint) -> TaskStep:
    return TaskStep(
        step_id=waypoint.waypoint_id,
        kind=TaskStepKind.DYNAMIC,
        goal=waypoint.description,
        allowed_side_effects=[],
        verification_spec=waypoint.arrival_spec,
        policy=TaskStepPolicy(
            policy_id=f"policy:{waypoint.waypoint_id}",
            description=f"Bounded actions to reach waypoint {waypoint.waypoint_id}.",
            max_iterations=3,
        ),
    )


def compile_sequence_to_plan(sequence: WaypointSequence) -> TaskPlan:
    return TaskPlan(
        plan_id=build_task_plan_id(),
        summary=(
            f"Waypoint sequence {sequence.sequence_id} "
            f"for behavior {sequence.behavior_label}."
        ),
        steps=[_compile_step(wp) for wp in sequence.waypoints],
    )
```

- [ ] **Step 4: 写子模块导出**

`mobiflow_agent/waypoint/__init__.py`:

```python
from mobiflow_agent.waypoint.compiler import compile_sequence_to_plan
from mobiflow_agent.waypoint.models import (
    PathConstraint,
    RendezvousSpec,
    Waypoint,
    WaypointSequence,
    WaypointStrength,
)

__all__ = [
    "PathConstraint",
    "RendezvousSpec",
    "Waypoint",
    "WaypointSequence",
    "WaypointStrength",
    "compile_sequence_to_plan",
]
```

- [ ] **Step 5: 运行测试,确认通过**

Run: `python -m pytest tests/waypoint/test_waypoint_compiler.py -q`
Expected: PASS(3 passed)

- [ ] **Step 6: 全量回归 + 提交**

Run: `python -m pytest -q`
Expected: 全绿(新增 9 条通过,既有测试不受影响)

```bash
git add mobiflow_agent/waypoint/__init__.py mobiflow_agent/waypoint/compiler.py tests/waypoint/test_waypoint_compiler.py
git commit -m "feat(waypoint): compile waypoint sequence into executable TaskPlan"
```

---

## 后续计划(不在本计划范围)

- **P2-1b**:`PathConstraintGuard`(读 `mobile_observation_summary` fact 的 `screen_id` 判定 `required_screens`/`forbidden_actions`)+ 图路由新增 `off_standard_path` 终态失败出口(改 `graph/nodes.py` decide 分支、`graph/routes.py` 的 `_STEP_ROUTES`/`_normalize_route`、`graph/builder.py` 条件路由目标集)+ 航点段时间线扩展(`runtime/trace_export.py`,产出设备无关的 `{waypoint_id, behavior_label, ...}`)。
- **P2-2**:Platform(Java)异构分派(`sequenceId` schema、per-target payload、count 限量 + 跨条目去重、`!busy` 过滤、`create_heterogeneous_run` 等 MCP 工具)。
- **P2-3**:对话入口(`IntentPlanner`/`DispatchPlan` schema、`resolve_sequence`/`draft_sequence`)+ Platform join deviceId 到航点时间线。
