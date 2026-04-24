# MobiFlow Agent Docs

## 文档目的

这里用于存放新 Agent 的设计文档、阶段方案和后续实现说明。

- 当前状态：`in_progress`
- 文档版本：`v0.3`
- 最近更新：`2026-04-23`

## 更新规则

- 先放设计，再放实现说明。
- 文档必须与根目录阶段治理文档和 `MobiFlow_Agent/` 下的实现骨架保持一致。
- 文档命名优先表达阶段或主题，避免使用含糊占位名。

## 当前约定

- 架构基线以仓库根目录文档为准。
- 阶段治理以根目录总方案、总进度和 `agent-phases/` 下的阶段计划为准。
- 旧 Agent 文档只作参考，不自动迁入此目录。
- 本目录下的 phase-1 / phase-2 文档是历史阶段设计基线，不代表当前实现只停留在阶段 2。
- 当前实现入口以 `MobiFlow_Agent/README.md`、根目录总方案、总进度和 `agent-phases/phase-5-plan.md` 为准。

## 当前文档

- `langgraph-task-runtime.md`
  - 说明 `mobiflow_agent.graph` 主 LangGraph 编排层、节点路由、使用方式和兼容策略
- `phase-1-architecture-baseline.md`
  - 冻结阶段 1 的角色职责、关键对象、Platform 对齐方式和 Executor 证据底线
- `phase-1-executor-evidence-baseline.md`
  - 基于现有协议和端侧实现，冻结阶段 1 的最小执行证据要求
- `phase-2-runtime-interface-baseline.md`
  - 冻结阶段 2 的最小 runtime state、Platform adapter 和阶段 3 首条实现切口
