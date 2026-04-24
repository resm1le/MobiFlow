# 文档导航

本目录保存 `AI_Mobile_Executor_Platform` 的权威文档。文档按“总览 / 架构 / 协议 / 运行时 / AI / 控制台 / 运维验证”分组。

## 总览

- [项目总览](./project-overview.md)
- [架构说明](./architecture.md)
- [数据模型](./data-model.md)

## 协议与运行时

- [控制面说明](./control-plane.md)
- [平台协议概览](./protocol.md)
- [Agent 工具接入说明](./agent-tool-server.md)
- [Android 端联调说明](./android-terminal.md)

## AI 与控制台

- [AI 服务说明](./ai-service.md)
- [控制台说明](./console.md)

## 运维与验证

- [运维与仓库治理](./operations.md)
- [验证指南](../integration/validation.md)

## 文档原则

- `/api/**`、`/executor/**`、`/tools/**` 的边界必须保持清晰
- 协议、数据模型和运行时语义发生正式变更时，先更新文档再更新实现
- 正式文档仅保留在根 `README.md`、`docs/` 和 `integration/validation.md`
- `node_modules`、`target`、缓存目录和临时导出文件不属于正式文档体系
