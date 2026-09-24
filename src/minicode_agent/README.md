# `minicode_agent`

这是 MiniCode Agent 的 Python 包根目录。它只负责导出版本信息；实际能力按职责拆分到下面的 bundle 中。

## Bundle 导航

| Bundle | 职责 | 入口 |
| --- | --- | --- |
| `runtime` | Agent Loop、消息模型、上下文预算、Harness 和 Preset | `AgentRuntime`、`AgentHarness` |
| `models` | 模型 Provider 协议、Fake Provider、OpenAI-compatible Provider | `ModelProvider` |
| `tools` | 结构化工具、参数校验、注册、权限前置检查和 Hook | `ToolRegistry` |
| `security` | 工作区路径边界和审批策略 | `Workspace`、`PermissionPolicy` |
| `execution` | POSIX Shell / PowerShell 检测、启动、超时和终止 | `ShellBackend` |
| `persistence` | Trace、SQLite Run Store、Checkpoint 和 Replay | `SqliteRunStore`、`SessionReplay` |
| `artifacts` | Git 变更和测试结果等运行产物提取 | `WorkspaceChangeTracker` |
| `evaluation` | 在临时工作区执行任务并用独立命令验收 | `EvaluationRunner` |
| `web` | FastAPI API、SSE 事件流和运行管理 | `create_app`、`RunManager` |

## 依赖方向

依赖大致从外向内收敛：CLI/Web 组装 `Harness`，Harness 组合 Runtime、Model、Tool 和 Persistence；Tools 依赖 Security/Execution，Persistence 依赖 Runtime 的数据模型。Runtime 不依赖 FastAPI 或 React，因此可以在 CLI、Web 和测试中复用。

## 修改建议

新增能力时优先放入对应 bundle，并通过协议或数据模型连接边界。不要在 `runtime/agent.py` 中直接加入 HTTP、SQLite 或终端交互逻辑；这样可以保持 Agent Loop 可测试、可替换，也方便后续增加 Provider、执行后端或其他入口。
