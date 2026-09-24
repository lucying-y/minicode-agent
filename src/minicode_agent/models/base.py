"""Interfaces implemented by model providers.

The Runtime speaks only these protocols.  A provider may use HTTP, a local
model, or a scripted response as long as it returns the shared runtime models.
The streaming protocol deliberately ends with one complete response so the
caller never has to infer whether a partial tool-call JSON value is executable.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from minicode_agent.runtime.types import Message, ModelResponse, ModelStreamChunk, ToolSchema


class ModelProvider(Protocol):
    """Translate runtime messages and tool schemas to a model API.

    Implementations should raise a provider-specific exception for transport or
    response-shape failures; the Runtime catches that failure and records a
    terminal `model_error` event.
    """

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolSchema],
    ) -> ModelResponse:
        """Return the model's next response."""
        ...


class StreamingModelProvider(ModelProvider, Protocol):
    """Optional provider capability for incremental model output.

    Text chunks are safe to display immediately.  Tool-call fragments and usage
    are accumulated by the provider and exposed in the final chunk.
    """

    supports_streaming: bool

    def stream_complete(
        self,
        messages: list[Message],
        tools: list[ToolSchema],
    ) -> AsyncIterator[ModelStreamChunk]:
        """Yield text deltas followed by one assembled response."""
        ...
