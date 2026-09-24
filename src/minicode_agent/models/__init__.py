"""Model provider interfaces and implementations.

This surface contains both the real OpenAI-compatible adapter and the
deterministic Fake Provider used by tests and demos.
"""

from minicode_agent.models.base import ModelProvider, StreamingModelProvider
from minicode_agent.models.fake import FakeModelProvider
from minicode_agent.models.openai_compatible import ModelProviderError, OpenAICompatibleProvider

__all__ = [
    "FakeModelProvider",
    "ModelProvider",
    "ModelProviderError",
    "OpenAICompatibleProvider",
    "StreamingModelProvider",
]
