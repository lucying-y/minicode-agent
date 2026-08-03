"""Interfaces implemented by model providers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
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
