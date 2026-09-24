# Models Bundle

`models` 把 Runtime 的 provider-neutral 消息转换为具体模型协议，并把响应转换回统一数据模型。

## 组件

- `base.py`：`ModelProvider` 和可选的 `StreamingModelProvider` 协议。
- `openai_compatible.py`：调用 `/chat/completions`，支持普通响应和 SSE 流式响应。
- `fake.py`：按队列返回预设响应，用于离线 Demo 和确定性测试。

## Provider 合约

普通 Provider 实现 `complete(messages, tools)`；流式 Provider 额外暴露 `supports_streaming=True` 和 `stream_complete()`。流式迭代器可以先返回文本 `delta`，最后必须返回包含完整文本、完整 ToolCall 和 TokenUsage 的 `ModelStreamChunk(response=...)`。

## 兼容性注意

OpenAI-compatible Provider 会把 `ToolSchema` 映射为 function tool，把 assistant 的工具调用和 tool 结果映射为 Chat Completions 消息。不同厂商对 usage、SSE chunk 和工具参数的细节可能不同，解析失败会转换为 `ModelProviderError`，不会让 Runtime 执行不完整的工具调用。
