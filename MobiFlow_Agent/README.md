# MobiFlow Agent

- 当前状态：`in_progress`
- 当前阶段：`阶段 8A`
- 阶段 8A 状态：`in_progress`
- 最近更新：`2026-04-23`
- 当前测试基线：`396 passed`

## 项目定位

MobiFlow Agent 是一个面向移动执行场景的任务执行系统。

在 MobiFlow 大系统中，Agent 是最上层智能任务层：

- Agent 负责规划、观察编排、执行提案、验证、恢复、记忆和评测。
- Platform 负责 canonical state、治理、审批、审计和协议。
- Android Executor 负责终端侧执行、事件和产物回传。

大系统文档入口见：[../docs/README.md](../docs/README.md)。

核心执行链：

- `goal -> plan -> observe -> execute -> verify`
- `goal -> plan -> observe -> recover -> verify`

任务完成必须基于 evidence-based verification，而不是工具返回成功或自然语言总结。

## 当前包结构

```text
mobiflow_agent/
  __init__.py
  common/
  task/
  control/
  agents/
  model/
  execution/
  memory/
  evaluation/
  runtime/
  graph/
  platform/
```

迁移后的包职责：

- `graph/` 是 LangGraph 主编排层，承载 runtime、nodes、routes、checkpoint 接入和 graph support ops。
- `control/` 只保留 dispatcher、policy 与 `TaskOrchestratorService` 兼容命名，不再承载主状态机。
- `runtime/` 继续承载 harness、checkpointing、context handoff/compression 等运行支撑能力。

## 包根公开入口

`mobiflow_agent` 保留 task-first 主入口，并公开当前稳定的控制面、模型层、memory、上下文压缩、harness 与 simulation/scenario 入口：

- `TaskOrchestratorService`
- `TaskGraphRuntime`
- `TaskGraphState`
- `build_task_orchestration_graph`
- `TaskSession`
- `TaskPlan`
- `TaskStep`
- `TaskStepPolicy`
- `TaskStatus`
- `TaskCompletionVerdict`
- `AgentRole`
- `RoleRequest`
- `RoleResult`
- `StepDecision`
- `StepDecisionType`
- `StepPolicyAgent`
- `ReplanDecision`
- `ReplanDecisionType`
- `RecoveryOutcome`
- `PlannerAgent`
- `ObserverAgent`
- `ExecutorAgent`
- `VerifierAgent`
- `RecoveryAgent`
- `ExecutionProposal`
- `ObservationView`
- `VerificationSpec`
- `VerificationVerdict`
- `EntityKind`
- `ModelProfile`
- `ModelSettings`
- `EmbeddingProfile`
- `RoleModelPolicy`
- `ModelRegistry`
- `ModelRegistryBuilder`
- `ModelRuntime`
- `ModelInvocationTrace`
- `EmbeddingClient`
- `EmbeddingRequest`
- `EmbeddingResponse`
- `OpenAICompatibleProviderConfig`
- `TaskMemoryRecord`
- `TaskMemoryRecordKind`
- `TaskMemoryRecordStatus`
- `TaskMemoryQuery`
- `TaskMemoryMatch`
- `TaskMemoryRetrievalResult`
- `TaskMemoryPolicy`
- `TaskMemoryGovernancePolicy`
- `TaskMemoryGovernanceDecision`
- `TaskMemoryGovernanceIssue`
- `TaskMemoryGovernanceReport`
- `TaskMemoryGovernanceService`
- `TaskMemoryQualityPolicy`
- `TaskMemoryQualityIssue`
- `TaskMemoryQualityDecision`
- `TaskMemoryQualityService`
- `TaskMemoryContext`
- `TaskMemoryRuntime`
- `TaskMemoryLegacyImportService`
- `TaskMemoryStore`
- `InMemoryTaskMemoryStore`
- `SqliteTaskMemoryStore`
- `ContextCompressionPolicy`
- `ContextCompressionResult`
- `ContextCompressionService`
- `ContextHandoff`
- `TaskHarnessApprovalRequest`
- `TaskHarnessRequest`
- `TaskHarnessJob`
- `TaskHarnessJobPolicy`
- `TaskHarnessResponse`
- `TaskHarnessService`
- `TaskHarnessStatus`
- `TaskHarnessStore`
- `TaskHarnessError`
- `TaskHarnessTransitionError`
- `TaskHarnessStoreError`
- `TaskHarnessSerializationError`
- `TaskHeartbeatRunner`
- `SessionContextDigest`
- `StepContextSummary`
- `SimulatedUiNode`
- `SimulatedScreen`
- `SimulatedTransition`
- `SimulatedMobileScenario`
- `SimulatedActionTrace`
- `SimulatedMobilePlatformAdapter`
- `ScenarioEvaluationCase`
- `ScenarioExpectation`
- `ScenarioEvaluationResult`
- `ScenarioEvaluationReport`
- `ScenarioQualityGate`
- `ScenarioEvaluationService`
- `ScenarioMemoryEvaluationService`
- `ScenarioMemoryComparisonResult`
- `ScenarioMemoryComparisonReport`
- `PlannerPromptBuilder`
- `RecoveryPromptBuilder`
- `VerifierPromptBuilder`

支撑能力继续从子包导入，例如：

- `mobiflow_agent.execution.recovery.execution`
- `mobiflow_agent.memory.case`
- `mobiflow_agent.memory.evaluation`
- `mobiflow_agent.runtime.state`
- `mobiflow_agent.model.providers`

## 最小调用面

```python
from mobiflow_agent import (
    EntityKind,
    ModelProfile,
    ModelRegistryBuilder,
    OpenAICompatibleProviderConfig,
    RoleModelPolicy,
    TaskGraphRuntime,
    VerificationSpec,
)

builder = ModelRegistryBuilder(
    profiles=[
        ModelProfile(name="planner-profile", provider="openai-compatible", model="gpt-4o-mini"),
        ModelProfile(name="verifier-profile", provider="openai-compatible", model="gpt-4o-mini"),
    ],
)
builder.register_openai_compatible(OpenAICompatibleProviderConfig.from_env())
registry = builder.build()

runtime = TaskGraphRuntime(
    model_registry=registry,
    role_model_policy=RoleModelPolicy(
        role_profiles={
            "planner": "planner-profile",
            "verifier": "verifier-profile",
        }
    ),
)

session = runtime.create_session(
    "Inspect blocked task",
    target_kind=EntityKind.RUN,
    target_id="run-123",
    verification_spec=VerificationSpec(...),
)

session = runtime.run(session)
```

`TaskOrchestratorService` 仍可导入，但它只是 graph-backed runtime 的兼容类名。新代码优先使用 `TaskGraphRuntime`。

## Memory / RAG 调用面

```python
from mobiflow_agent import (
    EmbeddingProfile,
    ModelRegistryBuilder,
    OpenAICompatibleProviderConfig,
    SqliteTaskMemoryStore,
    TaskMemoryGovernancePolicy,
    TaskMemoryGovernanceService,
    TaskMemoryPolicy,
    TaskMemoryRuntime,
    TaskGraphRuntime,
)

store = SqliteTaskMemoryStore("var/task-memory.sqlite3")

builder = ModelRegistryBuilder(
    embedding_profiles=[
        EmbeddingProfile(
            name="memory-embedding",
            provider="openai-compatible",
            model="text-embedding-3-small",
        )
    ]
)
builder.register_openai_compatible(OpenAICompatibleProviderConfig.from_env())
registry = builder.build()

memory_runtime = TaskMemoryRuntime(
    store=store,
    embedding_profile_name="memory-embedding",
    policy=TaskMemoryPolicy(require_evidence_for_writeback=True),
    governance_service=TaskMemoryGovernanceService(
        policy=TaskMemoryGovernancePolicy(default_ttl_ms=30 * 24 * 60 * 60 * 1000)
    ),
)

runtime = TaskGraphRuntime(
    model_registry=registry,
    memory_runtime=memory_runtime,
)
```

严格写回与 memory-on/off 场景对比：

```python
from mobiflow_agent import (
    InMemoryTaskMemoryStore,
    ScenarioMemoryEvaluationService,
    TaskMemoryRuntime,
)
from mobiflow_agent.evaluation.scenario import memory_writeback_quality_rejects_unknown_case

comparison = ScenarioMemoryEvaluationService(
    memory_runtime_factory=lambda: TaskMemoryRuntime(store=InMemoryTaskMemoryStore())
).compare_case(memory_writeback_quality_rejects_unknown_case())

assert comparison.quality_rejection_count >= 0
```

## Harness 调用面

```python
from mobiflow_agent import (
    EntityKind,
    SqliteTaskHarnessStore,
    TaskHarnessRequest,
    TaskHarnessService,
    TaskHeartbeatRunner,
    TaskGraphRuntime,
    VerificationSpec,
)

store = SqliteTaskHarnessStore("var/task-harness.sqlite3")
runtime = TaskGraphRuntime(...)
harness = TaskHarnessService(orchestrator=runtime, store=store)

response = harness.start(
    TaskHarnessRequest(
        goal="Inspect blocked task",
        target_kind=EntityKind.RUN,
        target_id="run-123",
        verification_spec=VerificationSpec(...),
    )
)

responses = TaskHeartbeatRunner(harness).run_once()
store.close()
```

## Scenario 调用面

```python
from mobiflow_agent import ScenarioEvaluationService
from mobiflow_agent.evaluation.scenario import login_success_case

result = ScenarioEvaluationService().run_case(login_success_case())

assert result.matched is True
assert result.final_response.status.value == "completed"
```

## 当前能力

- 阶段 6 的 checkpoint-ready 控制面保持稳定
- `model/` 是 provider-agnostic 的 generation + embedding 子系统
- `memory/` 已升级为 task-first 记忆子系统，支持 record / store / retrieval / strict writeback / quality / governance / evaluation
- `TaskGraphRuntime` 是 LangGraph 主编排层，并在 `planner / recovery / verifier` 前主动注入记忆上下文
- `DYNAMIC` step 支持层级计划内的动态 step policy，允许 bounded observe/decide/execute loop
- recovery 支持轻量 replan decision：retry、skip、handoff、fail
- verify 收口后可自动写回高价值 task memory，且默认经过 quality gate 防污染
- retrieval 默认只返回 `ACTIVE` 且未过期 memory，quarantined / expired / superseded 记录只用于治理审计
- legacy recovery memory 可通过导入服务迁移为 task-first memory record
- `runtime/context` 提供 step summary、session digest 与 cross-session `ContextHandoff`
- `runtime/harness` 是 task-first harness 正式入口
- `platform/simulation` 提供正式 simulated mobile runtime
- `evaluation/scenario` 提供 canonical scenario fixtures、quality gate、聚合报告与 memory-on/off 对比

## 当前边界

- 不做物理多 Agent / team-chat
- 不让模型直调工具
- `memory` 可以在 verify 后自动沉淀高价值记忆，但不直接改写 proposal / execution 决策
- `evaluation` 不直接主导 runtime
- 不把 LangGraph 升级为 Platform / Android Executor 的系统总框架
- heartbeat 只做到本地 / in-process 生产基线，不做分布式 worker claim、后台 daemon、Redis/Postgres queue
- 当前不做真实设备、ADB、uiautomator、截图、logcat 或外部观察接入

## 验证命令

在 [MobiFlow_Agent](/D:/developing/MobiFlow/MobiFlow_Agent) 下执行：

```powershell
python -m pytest -q
```

当前结果：

- `396 passed`
