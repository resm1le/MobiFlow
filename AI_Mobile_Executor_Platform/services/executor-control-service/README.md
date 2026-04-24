# executor-control-service

## 职责

`executor-control-service` 是 Platform 的主控制面，负责：

- executor ingress
- 调度与状态推进
- run / task / attempt 管理
- artifact metadata
- admin API
- tool runtime

## 本地启动

从仓库根目录执行：

```powershell
.\integration\scripts\start-control-service.ps1 -AdminAuthToken <admin-token>
```

## 测试

```powershell
mvn test
```

## 文档入口

- [架构说明](../../docs/architecture.md)
- [控制面说明](../../docs/control-plane.md)
- [平台协议概览](../../docs/protocol.md)
- [数据模型](../../docs/data-model.md)
- [运维与仓库治理](../../docs/operations.md)
