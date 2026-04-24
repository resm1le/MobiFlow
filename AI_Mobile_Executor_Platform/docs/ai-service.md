# AI 服务说明

## 角色

`executor-ai-service` 是 Platform 背后的结构化 AI 服务。它负责：

- run planning
- run summary
- failure triage

它只接受 control-service 的内部请求，不直接面向控制台、Agent 或设备。

## 当前端点

- `GET /internal/health`
- `POST /internal/run-plans`
- `POST /internal/failure-triage`
- `POST /internal/run-summaries`

## 行为特点

- 在调用模型前先校验请求结构
- 对模型结果做严格结构校验
- 本地开发默认可使用 stub provider
- 配置后可切到 OpenAI-compatible provider
- 对 provider 调用施加并发、重试和 cooldown 约束

## 边界

- 不调用设备
- 不创建 attempt
- 不直接写 control-plane 权威状态
- 不绕过 control-plane 做物化或副作用
- 不直接对外暴露 operator-facing API

## 本地运行

```powershell
.\integration\scripts\start-ai-service.ps1
```

## 测试

```powershell
cd services/executor-ai-service
mvn test
```
