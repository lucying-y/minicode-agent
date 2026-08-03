"""Deterministic model provider for tests and local demos."""

from collections import deque
from collections.abc import Iterable

from minicode_agent.runtime.types import Message, ModelResponse, ToolSchema


class FakeModelProvider:
    """Return scripted responses and record every request."""

    def __init__(self, responses: Iterable[ModelResponse]) -> None:
        self._responses = deque(responses)
        self.requests: list[tuple[list[Message], list[ToolSchema]]] = []

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolSchema],
    ) -> ModelResponse:
        self.requests.append((list(messages), list(tools)))
        if not self._responses:
            raise RuntimeError("FakeModelProvider has no scripted response left")
        return self._responses.popleft()

