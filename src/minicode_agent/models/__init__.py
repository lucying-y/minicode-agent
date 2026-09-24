"""模型 Provider 接口及其实现。

这里同时提供真实的 OpenAI-compatible 适配器，以及供测试和演示使用的确定性 Fake Provider。
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
