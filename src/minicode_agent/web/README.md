# Backend Web Bundle

这里是 FastAPI 后端，不是 `web/` 目录下的 React 前端。它把 Runtime 能力包装成 HTTP API，并负责异步运行、审批等待、取消、恢复和 SSE 事件订阅。

## 组件

- `models.py`：创建任务、审批、运行视图和健康检查的 API 数据模型。
- `manager.py`：`RunManager` 管理后台任务、内存中的活动句柄和 SQLite 持久化时间线。
- `app.py`：创建 FastAPI 路由、SSE 流和静态资源托管。

## 生命周期

创建任务后，Manager 立即写入 `run_queued`，后台执行 Runtime；事件同时写入 Run Store 和内存订阅队列。SSE 客户端断开不等于任务取消，之后可以通过历史 API 或 Replay 重新读取。审批模式为 `ask` 时，Manager 将运行置为 `waiting_approval`，收到决策后才继续。

前端代码和样式位于仓库根目录 `web/`，本次注释整理不修改该层。
