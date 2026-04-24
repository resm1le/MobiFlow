# Integration

本目录保存 Platform 的本地启动、验证脚本和示例 payload。

## 当前内容

- `payloads/`
  示例 task、device pool 和 run 创建 payload
- `scripts/`
  启动、管理和仓库治理检查脚本
- `validation.md`
  当前唯一权威的本地验证指南

## 本地验证流程

1. 启动基础设施
2. 启动 control-service
3. 启动 ai-service
4. 需要 UI 时启动 console-web
5. 按 [validation.md](./validation.md) 执行验证

## 常用脚本

- `scripts/check-repository-governance.ps1`
- `scripts/start-control-service.ps1`
- `scripts/start-ai-service.ps1`
- `scripts/start-console-web.ps1`
- `scripts/create-device-pool.ps1`
- `scripts/create-run.ps1`
- `scripts/query-run.ps1`
- `scripts/cancel-run.ps1`
- `scripts/run-local-regression.ps1`
