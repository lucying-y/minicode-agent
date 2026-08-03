"""Interfaces implemented by model providers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from minicode_agent.runtime.types import Message, ModelResponse, ModelStreamChunk, ToolSchema


class ModelProvider(Protocol):
    """Translate runtime messages and tool schemas to a model API."""

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolSchema],
    ) -> ModelResponse:
        """Return the model's next response."""
        ...


class StreamingModelProvider(ModelProvider, Protocol):
    """Optional provider capability for incremental model output."""

    supports_streaming: bool

    def stream_complete(
        self,
        messages: list[Message],
        tools: list[ToolSchema],
    ) -> AsyncIterator[ModelStreamChunk]:
        """Yield text deltas followed by one assembled response."""
        ...
