"""供测试和本地演示使用的确定性模型 Provider。

Fake Provider 有意采用严格行为：每个请求恰好消费一个预设响应。响应不足时会明确失败，
从而发现意外增加的 Runtime 步骤，而不是静默产生具有误导性的成功测试。
"""

import asyncio
from collections import deque
from collections.abc import AsyncIterator, Iterable

from minicode_agent.runtime.types import Message, ModelResponse, ModelStreamChunk, ToolSchema


class FakeModelProvider:
    """返回预设响应并记录每次请求。

    当 ``streaming=True`` 时，同一个响应会拆分为文本增量和最终完整响应，使测试无需网络
    即可覆盖真实的 Runtime 流式路径。
    """

    def __init__(
        self,
        responses: Iterable[ModelResponse],
        *,
        streaming: bool = False,
        stream_chunk_size: int = 12,
        stream_delay_seconds: float = 0.0,
    ) -> None:
        self._responses = deque(responses)
        self.requests: list[tuple[list[Message], list[ToolSchema]]] = []
        self.supports_streaming = streaming
        self.stream_chunk_size = max(1, stream_chunk_size)
        self.stream_delay_seconds = max(0.0, stream_delay_seconds)

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolSchema],
    ) -> ModelResponse:
        self.requests.append((list(messages), list(tools)))
        if not self._responses:
            raise RuntimeError("FakeModelProvider has no scripted response left")
        return self._responses.popleft()

    async def stream_complete(
        self,
        messages: list[Message],
        tools: list[ToolSchema],
    ) -> AsyncIterator[ModelStreamChunk]:
        """依次产生确定性分片，最后返回原始完整响应。"""
        self.requests.append((list(messages), list(tools)))
        if not self._responses:
            raise RuntimeError("FakeModelProvider has no scripted response left")
        response = self._responses.popleft()
        for start in range(0, len(response.content), self.stream_chunk_size):
            if self.stream_delay_seconds:
                await asyncio.sleep(self.stream_delay_seconds)
            yield ModelStreamChunk(delta=response.content[start : start + self.stream_chunk_size])
        yield ModelStreamChunk(response=response)
