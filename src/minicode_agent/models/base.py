"""模型 Provider 需要实现的接口。

Runtime 只依赖这些协议。Provider 可以使用 HTTP、本地模型或预设响应，只要返回共享的
Runtime 数据模型即可。流式协议有意以一个完整响应结束，因此调用方不需要判断不完整的
工具调用 JSON 是否可以执行。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from minicode_agent.runtime.types import Message, ModelResponse, ModelStreamChunk, ToolSchema


class ModelProvider(Protocol):
    """在 Runtime 消息、工具 Schema 与模型 API 之间进行转换。

    传输失败或响应结构异常时，实现应抛出 Provider 专用异常；Runtime 会捕获异常并记录终态
    `model_error` 事件。
    """

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolSchema],
    ) -> ModelResponse:
        """Return the model's next response."""
        ...


class StreamingModelProvider(ModelProvider, Protocol):
    """用于模型增量输出的可选 Provider 能力。

    文本分片可以立即显示；工具调用片段和用量由 Provider 累积，并在最终分片中统一返回。
    """

    supports_streaming: bool

    def stream_complete(
        self,
        messages: list[Message],
        tools: list[ToolSchema],
    ) -> AsyncIterator[ModelStreamChunk]:
        """Yield text deltas followed by one assembled response."""
        ...
