"""Deterministic model provider for tests and local demos."""

import asyncio
from collections import deque
from collections.abc import AsyncIterator, Iterable

from minicode_agent.runtime.types import Message, ModelResponse, ModelStreamChunk, ToolSchema


class FakeModelProvider:
    """Return scripted responses and record every request."""

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
        self.requests.append((list(messages), list(tools)))
        if not self._responses:
            raise RuntimeError("FakeModelProvider has no scripted response left")
        response = self._responses.popleft()
        for start in range(0, len(response.content), self.stream_chunk_size):
            if self.stream_delay_seconds:
                await asyncio.sleep(self.stream_delay_seconds)
            yield ModelStreamChunk(delta=response.content[start : start + self.stream_chunk_size])
        yield ModelStreamChunk(response=response)
