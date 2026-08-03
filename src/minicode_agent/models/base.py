"""Interfaces implemented by model providers."""

from typing import Protocol

from minicode_agent.runtime.types import Message, ModelResponse, ToolSchema


class ModelProvider(Protocol):
    """Translate runtime messages and tool schemas to a model API."""

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolSchema],
    ) -> ModelResponse:
        """Return the model's next response."""
        ...

