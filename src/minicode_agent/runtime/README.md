# Runtime Bundle

`runtime` 是 Agent 的核心状态机。它把一次用户任务转换为一系列模型请求、工具执行和终态事件。

## 核心组件

- `types.py`：Provider、Tool 和持久化之间共享的 Pydantic 数据模型。
- `agent.py`：`AgentRuntime`，负责有界的模型-工具循环、流式回调、停止条件和 Checkpoint 边界。
- `context.py`：按估算 Token 预算裁剪历史，同时保留完整的 assistant/tool 执行块。
- `harness.py`：`AgentHarness`，只负责依赖组合，不拥有执行循环。
- `presets.py`：`minimal`、`standard`、`review` 三种工具集合和上下文上限。

## 一次运行的状态流

1. `run()` 创建 system/user 消息，写入 `run_started` 和初始 Checkpoint。
2. `_continue()` 先调用 `ContextManager.prepare()`，再请求 Provider。
3. 无工具调用时直接完成；有工具调用时逐个经过 Registry 执行并追加 `tool` 消息。
4. 一轮所有工具完成后保存一致 Checkpoint，进入下一步。
5. 完成、失败、超步数、超 Token 或工具错误都会通过 `_finish()` 写入终态。

## 设计边界

Runtime 只依赖 `ModelProvider` 和 `ToolExecutor` 协议，不知道具体 HTTP、文件系统或数据库实现。`Checkpoint` 是可继续执行的最新一致状态，`Trace/Event Log` 是观察事实；两者不能混用。模型流式输出只用于 UI 增量展示，完整 `ModelResponse` 到达前不会执行半截工具参数。
