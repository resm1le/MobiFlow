# Apps Workspace

本目录保存 Platform 的前端应用。

## 当前应用

- `executor-console-web/`
  面向运维和观察的控制台

## 共享规则

- 前端应用只通过 control-plane API 工作
- 不直接访问设备
- 不直接调用 AI service

## 文档入口

- [控制台说明](../docs/console.md)
- [平台协议概览](../docs/protocol.md)
