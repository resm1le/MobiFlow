# Services Workspace

本目录保存 Platform 的后端服务。

## 当前服务

- `executor-control-service/`
  权威控制面，负责平台状态、协议和治理
- `executor-ai-service/`
  结构化 AI 服务，负责 planning、summary 和 triage

## 共享规则

- control-service 持有平台权威状态
- AI service 必须通过 control-service 被消费
- 协议或数据模型变更要先更新文档

## 文档入口

- [控制面说明](../docs/control-plane.md)
- [AI 服务说明](../docs/ai-service.md)
- [数据模型](../docs/data-model.md)
