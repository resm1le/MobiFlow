# 运维与仓库治理

## 正式文档边界

本仓库的正式文档只保留在：

- 根 `README.md`
- `docs/`
- [integration/validation.md](../integration/validation.md)

以下内容不属于正式文档体系：

- `node_modules`
- `target`
- `dist`
- `.m2-repo*`
- 临时日志、截图、导出文件和本地缓存

## 长期维护原则

- control-plane 是平台状态的唯一权威来源
- `/api/**`、`/executor/**`、`/tools/**` 的职责边界必须保持清晰
- 协议、状态机、数据模型发生正式变更时，先更新文档再更新实现
- 不把临时改造计划和草稿长期保留在正式 docs 中

## 本地环境约定

- control-service: `http://127.0.0.1:8080`
- ai-service: `http://127.0.0.1:8081`
- console-web: `http://127.0.0.1:5173`
- MySQL: `127.0.0.1:13306`
- Redis: `127.0.0.1:16379`
- MinIO API: `127.0.0.1:9000`
- MinIO Console: `127.0.0.1:9001`

## 常用启动命令

```powershell
docker compose -f services/executor-control-service/docker-compose.local.yml up -d
.\integration\scripts\start-control-service.ps1 -AdminAuthToken <admin-token>
.\integration\scripts\start-ai-service.ps1
.\integration\scripts\start-console-web.ps1 -BearerToken <admin-token>
```

## 文档联动要求

- 协议变更：同步更新 [protocol.md](./protocol.md)
- 控制面行为变更：同步更新 [control-plane.md](./control-plane.md)
- Agent 接入语义变更：同步更新 [agent-tool-server.md](./agent-tool-server.md)
- 验证路径变更：同步更新 [../integration/validation.md](../integration/validation.md)
