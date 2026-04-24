# 控制台说明

## 角色

`executor-console-web` 是面向运维和观察的 Web 控制台。它只通过 control-plane 的 `/api/**` 工作。

## 当前范围

- device 列表与详情
- device pool 列表与创建
- run 列表、创建、详情与取消
- task 列表、创建、详情与取消
- attempt 列表与详情
- artifact 列表与下载
- AI run plan 评审与物化
- AI run summary 评审
- AI failure triage 评审
- device command 与 resume

## 技术栈

- React
- TypeScript
- Vite
- TanStack Router
- TanStack Query

## 边界

- 只调用 `/api/**`
- 不直接访问 Android 设备
- 不直接调用 AI service
- 不暴露对象存储直链

## 本地开发

从 `.env.example` 创建 `.env`，并设置：

- `VITE_CONTROL_API_BASE_URL`
- `VITE_CONTROL_API_BEARER_TOKEN`

然后运行：

```powershell
.\integration\scripts\start-console-web.ps1 -BearerToken <admin-token>
```
