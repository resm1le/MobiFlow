# executor-ai-service

## 职责

`executor-ai-service` 是 Platform 背后的结构化 AI 服务，负责：

- run planning
- run summary
- failure triage

## 本地启动

从仓库根目录执行：

```powershell
.\integration\scripts\start-ai-service.ps1
```

## 测试

```powershell
mvn test
```

## 文档入口

- [AI 服务说明](../../docs/ai-service.md)
- [架构说明](../../docs/architecture.md)
- [运维与仓库治理](../../docs/operations.md)
