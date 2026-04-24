# executor-console-web

## 职责

`executor-console-web` 是 Platform 的运维和观察控制台，负责浏览平台状态并执行受控 admin 操作。

## 环境变量

从 `.env.example` 创建本地 `.env`，并设置：

- `VITE_CONTROL_API_BASE_URL`
- `VITE_CONTROL_API_BEARER_TOKEN`

## 常用命令

```powershell
npm install
npm run dev
npm run test
npm run build
```

## 边界

- 只使用 control-plane `/api/**`
- 不直接连接设备
- 不直接调用 AI service

## 文档入口

- [控制台说明](../../docs/console.md)
- [平台协议概览](../../docs/protocol.md)
- [运维与仓库治理](../../docs/operations.md)
