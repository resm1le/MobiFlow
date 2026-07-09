# A1/A3 死代码清除实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 删除 MobiFlow_Agent 中生产不可达的"第二套恢复子系统"(A3)与"死的状态反向映射"(A1),把仍存活的类型迁移到干净位置,让"哪套是活路径"变得一目了然。

**Architecture:** 这**不是重写**——经实证核实(见 `docs/superpowers/specs` 中定位基准 + 本次验证),`governed/`+`blocked_run/` 恢复图、`apply_runtime_state`、`RecoveryFollowupDriverService` 在生产中零调用,仅测试触及。真正的活路径是主图跑在 `TaskSession` 上,恢复只经 `FailureTriageGuidanceService`。因此本计划是**分层删除 + 类型迁移**:先把两个仍被生产依赖的存活类型(`RecoveryFollowupDriverDecision` 枚举、`GovernedRecoveryExecutionResponse` 的替代)下沉到不依赖死代码的位置,再删死代码子树,最后删死的反向映射。

**Tech Stack:** Python 3.11 · pydantic v2 · langgraph · pytest

## Global Constraints

- **绝不触碰活路径**:主图 `graph/builder.py:46`(`StateGraph(TaskGraphState)`)、`agents/recovery.py`(仅用 `FailureTriageGuidanceService`)、`execution/recovery/triage.py` 一律不改。
- **必须保留**(有活生产消费者):`runtime/state.py` 的 `AgentRuntimeState` 类 + `RuntimeLifecycle`/`ConfirmationState`/`CallerContext`/`PendingExecution`/`RecoveryExecutionContext`/`RecoveryObservationResult` 六个类型;`graph/projection_support.py` 的 `export_runtime_state`;harness DTO 的 `runtime_state` 字段。理由:`evaluation/scenario/quality_gate.py:85-90` 活读取 + 已序列化进 SQLite(`TASK_HARNESS_SCHEMA_VERSION = 1`)。
- **存储 schema 不升版**:只删 `apply`(写回)路径,不动 `export`(读出)与已落库字段,故 `TASK_HARNESS_SCHEMA_VERSION` 保持 `1`,旧记录仍可读。
- **测试命令**:当前解释器无 pytest。每个任务运行测试前先确保安装:`python -m pip install -e '.[dev]'`(pyproject 已声明 `dev = ["pytest>=7.4"]`),此后用 `python -m pytest`。
- **每步一提交**,提交信息用英文祈使句,不加 `--no-verify`。
- **删除即彻底**:不留 `# removed` 注释、不留兼容 re-export shim(定位基准明确不要向后兼容 hack)。

---

## 文件结构(改动地图)

**新增:**
- `mobiflow_agent/execution/followup/decisions.py` — 存放 `RecoveryFollowupDriverDecision` 枚举(从 `driver.py` 下沉,切断 memory→死driver 的反向依赖,对应 A8)。

**修改:**
- `mobiflow_agent/memory/{vector,case,embedding,catalog}.py` — 改 import 指向新 `decisions.py`。
- `mobiflow_agent/runtime/harness/{models,service}.py` — 改 import 指向新 `decisions.py`。
- `mobiflow_agent/evaluation/{replay.py,benchmark/suite.py}` — 改 import 指向新 `decisions.py`。
- `mobiflow_agent/graph/projection_support.py` — 删 `apply_runtime_state` + `_from_runtime_lifecycle` 反向表,保留 `export_runtime_state` + `_to_runtime_lifecycle`。
- `mobiflow_agent/control/orchestrator/service.py` / `graph/runtime.py` — 若暴露了 `apply_runtime_state` 转发,一并删。
- `tests/control/test_task_orchestrator_service.py` — 删 `test_..._runtime_projection_roundtrips_...`(370-433)中依赖 `apply` 的部分。

**删除(整文件):**
- `mobiflow_agent/execution/recovery/governed/`(8 文件)
- `mobiflow_agent/execution/recovery/blocked_run/`(6 文件)
- `mobiflow_agent/execution/recovery/execution.py`(re-export shim)
- `mobiflow_agent/execution/recovery/proposal.py`、`materializer.py`、`common.py`(仅 Path B 用)
- `mobiflow_agent/execution/followup/driver.py`(`RecoveryFollowupDriverService` 死;枚举已迁出)
- 对应测试:`tests/execution/test_governed_recovery_execution_service.py`、`test_cancel_blocked_run_service.py`、`test_cancel_blocked_run_graph.py`、`test_governed_recovery_proposal_service.py`、`test_recovery_followup_driver_service.py`

> **保留不动的测试**:`tests/runtime/test_runtime_state.py` 全测 `AgentRuntimeState`(活),不删。

---

## Task 1: 建立测试基线

**Files:**
- 无改动(仅验证环境)

**Interfaces:**
- Produces: 一个绿色的 pytest 基线,后续每个删除任务都以"基线里通过的活测试仍通过"为验收。

- [ ] **Step 1: 安装 dev 依赖**

Run:
```bash
cd /Users/dengqiuhan.1/code/MobiFlow/MobiFlow_Agent
python -m pip install -e '.[dev]'
```
Expected: 成功安装 pytest。

- [ ] **Step 2: 跑全量测试,记录基线**

Run: `python -m pytest -q`
Expected: 全绿(50 个测试文件)。若有预存失败,记下失败清单——后续只需保证"原本通过的不因删除而变红"。

- [ ] **Step 3: 记录待删测试当前通过**

Run:
```bash
python -m pytest tests/execution/test_governed_recovery_execution_service.py tests/execution/test_cancel_blocked_run_service.py tests/execution/test_cancel_blocked_run_graph.py tests/execution/test_governed_recovery_proposal_service.py tests/execution/test_recovery_followup_driver_service.py -q
```
Expected: 这些死代码测试当前 PASS(确认它们是"测试专用的死代码"而非坏代码)。

---

## Task 2: 下沉 `RecoveryFollowupDriverDecision` 枚举,切断 memory 反向依赖

**Files:**
- Create: `mobiflow_agent/execution/followup/decisions.py`
- Modify: `mobiflow_agent/memory/vector.py:11`, `memory/case.py:11`, `memory/embedding.py:11`, `memory/catalog.py:14`, `runtime/harness/models.py:8`, `runtime/harness/service.py:8`, `evaluation/replay.py:11`, `evaluation/benchmark/suite.py:12`
- Modify: `mobiflow_agent/execution/followup/driver.py`(改为从新模块 re-import,本任务暂不删 driver)

**Interfaces:**
- Produces: `mobiflow_agent.execution.followup.decisions.RecoveryFollowupDriverDecision`(枚举,值不变:`SCHEDULE_NEXT`/`HANDOFF_ONLY`/`COMPLETE`/`NO_FOLLOWUP`)。

- [ ] **Step 1: 写失败测试(验证新模块存在且值不变)**

在 `tests/execution/test_recovery_followup_decisions.py` 新建:
```python
from mobiflow_agent.execution.followup.decisions import RecoveryFollowupDriverDecision


def test_decision_enum_values_unchanged() -> None:
    assert RecoveryFollowupDriverDecision.SCHEDULE_NEXT.value == "schedule_next"
    assert RecoveryFollowupDriverDecision.HANDOFF_ONLY.value == "handoff_only"
    assert RecoveryFollowupDriverDecision.COMPLETE.value == "complete"
    assert RecoveryFollowupDriverDecision.NO_FOLLOWUP.value == "no_followup"
    assert {m.value for m in RecoveryFollowupDriverDecision} == {
        "schedule_next", "handoff_only", "complete", "no_followup",
    }
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/execution/test_recovery_followup_decisions.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'mobiflow_agent.execution.followup.decisions'`

- [ ] **Step 3: 创建新模块**

写 `mobiflow_agent/execution/followup/decisions.py`:
```python
from __future__ import annotations

"""Recovery follow-up decision enum, kept free of any execution/graph dependency."""

from enum import Enum


class RecoveryFollowupDriverDecision(str, Enum):
    SCHEDULE_NEXT = "schedule_next"
    HANDOFF_ONLY = "handoff_only"
    COMPLETE = "complete"
    NO_FOLLOWUP = "no_followup"
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/execution/test_recovery_followup_decisions.py -q`
Expected: PASS

- [ ] **Step 5: 把 8 个生产消费者的 import 改指向新模块**

在这 8 个文件中,把 `from mobiflow_agent.execution.followup.driver import RecoveryFollowupDriverDecision` 改为 `from mobiflow_agent.execution.followup.decisions import RecoveryFollowupDriverDecision`:
`memory/vector.py`, `memory/case.py`, `memory/embedding.py`, `memory/catalog.py`, `runtime/harness/models.py`, `runtime/harness/service.py`, `evaluation/replay.py`, `evaluation/benchmark/suite.py`

- [ ] **Step 6: 让 driver.py 从新模块引入(过渡,本任务不删 driver)**

编辑 `mobiflow_agent/execution/followup/driver.py`:删除其中 `class RecoveryFollowupDriverDecision(str, Enum): ...`(21-25 行)的定义,改为 `from mobiflow_agent.execution.followup.decisions import RecoveryFollowupDriverDecision`。

- [ ] **Step 7: 跑全量测试**

Run: `python -m pytest -q`
Expected: 与 Task 1 基线同样全绿(memory/harness/evaluation 测试仍过,新枚举测试过)。

- [ ] **Step 8: Commit**

```bash
git add mobiflow_agent/execution/followup/decisions.py mobiflow_agent/memory/ mobiflow_agent/runtime/harness/ mobiflow_agent/evaluation/ mobiflow_agent/execution/followup/driver.py tests/execution/test_recovery_followup_decisions.py
git commit -m "Extract RecoveryFollowupDriverDecision into dependency-free module"
```

---

## Task 3: 删除 `apply_runtime_state` 死的反向映射(A1)

**Files:**
- Modify: `mobiflow_agent/graph/projection_support.py`(删 `apply_runtime_state` + `_from_runtime_lifecycle`)
- Modify: `mobiflow_agent/control/orchestrator/service.py` 和/或 `mobiflow_agent/graph/runtime.py`(删对 `apply_runtime_state` 的转发,若有)
- Modify: `tests/control/test_task_orchestrator_service.py`(删 roundtrip 用例中依赖 `apply` 的断言)

**Interfaces:**
- Consumes: `export_runtime_state`(保留不动)。
- Produces: projection 层只剩单向 export;`apply_runtime_state` 及反向枚举表不复存在。

- [ ] **Step 1: 确认 `apply_runtime_state` 生产零调用**

Run: `grep -rn "apply_runtime_state" mobiflow_agent/`
Expected: 仅 `graph/projection_support.py` 定义处 + 可能的 `control/orchestrator/service.py`/`graph/runtime.py` 转发。**若出现任何其他生产文件调用,停止本任务并上报**(说明验证前提被推翻)。

- [ ] **Step 2: 删除 roundtrip 测试中依赖 apply 的部分**

编辑 `tests/control/test_task_orchestrator_service.py`:删除函数 `test_task_orchestrator_service_runtime_projection_roundtrips_waiting_and_verifying_state`(约 370-433 行整个函数)。保留其余测试(包括 531 行的 digest/handoff roundtrip,它不依赖 `apply_runtime_state`)。

- [ ] **Step 3: 跑测试确认该用例已移除、其余通过**

Run: `python -m pytest tests/control/test_task_orchestrator_service.py -q`
Expected: PASS,且测试数比之前少 1。

- [ ] **Step 4: 删除 `apply_runtime_state` 与反向枚举表**

编辑 `mobiflow_agent/graph/projection_support.py`:删除 `apply_runtime_state` 方法/函数、`_from_runtime_lifecycle` 映射表(72-83 行区域)。保留 `export_runtime_state` 与 `_to_runtime_lifecycle`。

- [ ] **Step 5: 删除转发(若存在)**

Run: `grep -rn "apply_runtime_state" mobiflow_agent/`
若 `control/orchestrator/service.py` 或 `graph/runtime.py` 有转发方法,删除之。再次 grep 应只余空。

- [ ] **Step 6: 跑全量测试**

Run: `python -m pytest -q`
Expected: 全绿(除 Task 3 Step 2 删掉的 1 个用例)。

- [ ] **Step 7: Commit**

```bash
git add mobiflow_agent/graph/projection_support.py tests/control/test_task_orchestrator_service.py
git commit -m "Remove dead apply_runtime_state reverse projection and its lossy enum table"
```

---

## Task 4: 迁移 `GovernedRecoveryExecutionResponse` 依赖,删除死的 followup driver

**Files:**
- Delete: `mobiflow_agent/execution/followup/driver.py`
- Delete: `tests/execution/test_recovery_followup_driver_service.py`
- Modify: `mobiflow_agent/evaluation/replay.py`(移除对 `GovernedRecoveryExecutionResponse` 的类型注解依赖)

**Interfaces:**
- Consumes: `RecoveryFollowupDriverDecision`(现来自 `decisions.py`,Task 2 已迁)。
- Produces: `execution/followup/` 不再依赖 `execution/recovery/execution.py` shim。

- [ ] **Step 1: 确认 `RecoveryFollowupDriverService` 生产零实例化**

Run: `grep -rn "RecoveryFollowupDriverService\|start_from_execution" mobiflow_agent/`
Expected: 仅 `execution/followup/driver.py` 定义处。**若有其他生产调用,停止并上报。**

- [ ] **Step 2: 查清 replay.py 对 GovernedRecoveryExecutionResponse 的用法**

Run: `grep -n "GovernedRecoveryExecutionResponse" mobiflow_agent/evaluation/replay.py`
读取上下文。若仅作类型注解(未实际构造该类型的对象),将该注解改为其实际承载的活类型或 `object`/删除注解;若有构造,停止并上报(说明它并非死代码)。

- [ ] **Step 3: 移除 replay.py 的死类型 import**

编辑 `mobiflow_agent/evaluation/replay.py`:删除 `from mobiflow_agent.execution.recovery.execution import GovernedRecoveryExecutionResponse`(11 行附近)及其注解用法(按 Step 2 结论处理)。

- [ ] **Step 4: 删除死的 driver 与其测试**

Run:
```bash
git rm mobiflow_agent/execution/followup/driver.py tests/execution/test_recovery_followup_driver_service.py
```

- [ ] **Step 5: 修复因删 driver.py 断裂的 import**

Run: `grep -rn "followup.driver import\|followup import driver" mobiflow_agent/ tests/`
对每个仍从 `followup.driver` 引入 `RecoveryFollowupDriverJob`/`RecoveryFollowupDriverResponse`/`RecoveryFollowupDriverService` 的**生产**文件:若确认为死引用则删除;若为活引用则停止上报。(基于验证,预期只有测试引用,已随 Step 4 删除。)

- [ ] **Step 6: 跑全量测试**

Run: `python -m pytest -q`
Expected: 全绿(比基线少 `test_recovery_followup_driver_service.py`)。

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "Delete dead RecoveryFollowupDriverService and its response-type coupling"
```

---

## Task 5: 删除 governed / blocked_run 恢复图子树(A3)

**Files:**
- Delete: `mobiflow_agent/execution/recovery/governed/`(整目录 8 文件)
- Delete: `mobiflow_agent/execution/recovery/blocked_run/`(整目录 6 文件)
- Delete: `mobiflow_agent/execution/recovery/proposal.py`、`materializer.py`、`common.py`
- Delete: `mobiflow_agent/execution/recovery/execution.py`(re-export shim)
- Delete: `tests/execution/test_governed_recovery_execution_service.py`、`test_cancel_blocked_run_service.py`、`test_cancel_blocked_run_graph.py`、`test_governed_recovery_proposal_service.py`

**Interfaces:**
- Consumes: 无(本任务纯删除,前置任务已切断所有活引用)。
- Produces: `execution/recovery/` 只剩活路径依赖(`triage.py` 及其所需)。

- [ ] **Step 1: 最终可达性确认(删除前的安全闸)**

Run:
```bash
grep -rn "execution.recovery.governed\|execution.recovery.blocked_run\|execution.recovery.execution\|execution.recovery.proposal\|execution.recovery.materializer\|execution.recovery.common\|build_governed_recovery\|build_cancel_blocked_run" mobiflow_agent/ | grep -v "^mobiflow_agent/execution/recovery/\(governed\|blocked_run\|execution.py\|proposal.py\|materializer.py\|common.py\)"
```
Expected: **空**(除被删子树内部的自引用外,无任何外部生产引用)。若有输出,逐条判定;非死引用则停止上报。

- [ ] **Step 2: 删除死代码子树与其测试**

Run:
```bash
git rm -r mobiflow_agent/execution/recovery/governed mobiflow_agent/execution/recovery/blocked_run
git rm mobiflow_agent/execution/recovery/proposal.py mobiflow_agent/execution/recovery/materializer.py mobiflow_agent/execution/recovery/common.py mobiflow_agent/execution/recovery/execution.py
git rm tests/execution/test_governed_recovery_execution_service.py tests/execution/test_cancel_blocked_run_service.py tests/execution/test_cancel_blocked_run_graph.py tests/execution/test_governed_recovery_proposal_service.py
```

- [ ] **Step 3: 清理 `execution/recovery/__init__.py` 的死 re-export**

Run: `grep -n "governed\|blocked_run\|proposal\|materializer\|common\|execution" mobiflow_agent/execution/recovery/__init__.py`
删除其中指向已删模块的 import / `__all__` 条目,保留 `triage` 等活条目。

- [ ] **Step 4: 全量 import 完整性检查**

Run: `python -c "import mobiflow_agent.graph.builder, mobiflow_agent.intake.service, mobiflow_agent.runtime.harness.service, mobiflow_agent.evaluation.scenario.quality_gate, mobiflow_agent.agents.recovery"`
Expected: 无 ImportError(活路径全部可导入)。

- [ ] **Step 5: 跑全量测试**

Run: `python -m pytest -q`
Expected: 全绿(比基线少上述 4 个死测试文件;活测试无一变红)。

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "Remove unreachable governed/blocked-run recovery subsystem (A3)"
```

---

## Task 6: 验证核心命题仪表未受损 + 收尾

**Files:**
- 无改动(端到端验证)

**Interfaces:**
- Consumes: 前 5 个任务的成果。
- Produces: 确认 scenario 质量门禁(命题验证工具)仍完整工作。

- [ ] **Step 1: 确认 quality_gate 的 runtime_state 读取路径仍活**

Run: `python -m pytest tests/evaluation/ -q`
Expected: 全绿。`evaluation/scenario/quality_gate.py:_recovery_path_observed` 依赖的 `response.runtime_state.recovery_summary/recovery_execution/recovery_observation` 仍可用(`AgentRuntimeState` + `export_runtime_state` 已保留)。

- [ ] **Step 2: 确认 harness 持久化往返仍可用(存储 schema 未破)**

Run: `python -m pytest tests/runtime/test_task_harness.py -q`
Expected: 全绿。`TaskHarnessJob.runtime_state` 序列化/反序列化不受影响,`TASK_HARNESS_SCHEMA_VERSION` 仍为 1。

- [ ] **Step 3: 全量回归**

Run: `python -m pytest -q`
Expected: 全绿。

- [ ] **Step 4: 统计删除成效**

Run:
```bash
git diff --stat 789d18b HEAD | tail -5
grep -rc "" mobiflow_agent/execution/recovery/*.py mobiflow_agent/execution/recovery/**/*.py 2>/dev/null | wc -l
```
Expected: 显示净删除约 2000+ 行;`execution/recovery/` 只剩活文件(`triage.py`、`__init__.py` 等)。

- [ ] **Step 5: 最终提交(如有 __init__ 等收尾改动)**

```bash
git add -A
git commit -m "Confirm proposition instrumentation intact after dead-code removal" || echo "nothing to commit"
```

---

## Self-Review

- **Spec 覆盖**:定位基准第一梯队 = A1 + A3。A3 = Task 4+5(删 driver + 删子树);A1 = Task 3(删 `apply` 反向映射)。A8(memory 反向依赖)顺带由 Task 2 修复。✓
- **Placeholder 扫描**:无 TBD/TODO;每个删除步骤给出确切 `git rm` 路径与确切 grep 命令;每个 grep 都有"若非空则停止上报"的守卫。✓
- **类型一致性**:`RecoveryFollowupDriverDecision` 值(4 个)在 Task 2 定义并全程一致;保留类型清单在 Global Constraints 固定。✓
- **顺序安全**:先迁移存活类型(T2)→ 删死映射(T3)→ 删依赖存活类型的死 driver(T4)→ 删无外部引用的子树(T5)→ 验证仪表(T6)。每步删除前都有可达性 grep 闸门。✓

## 关键风险与缓解

- **最大风险**:验证基于当前代码快照;若实现时代码已变,某个"死"引用可能变活。**缓解**:每个删除任务的 Step 1 都是 grep 可达性闸门,非空即停止上报,不盲删。
- **存储兼容**:只删 `apply`(写回),`export` 与已落库字段保留,`schema_version` 不变 → 旧 SQLite 记录仍可读(Task 6 Step 2 验证)。
- **命题仪表**:`AgentRuntimeState` 因 quality_gate 活读取而**刻意保留**,不在删除范围——这是本计划与"全删 AgentRuntimeState"的关键区别。
