"""MiniCode Agent Runtime 的可组合能力 bundle。

Harness 是依赖组合边界：调用方在这里选择模型、工具执行器、持久化 Sink 和限制，然后获得
统一的 `AgentRuntime`。把组装逻辑放在循环之外，可以让 Preset 和测试 fixture 保持简单，
而不必给状态机增加条件分支。
"""

from collections.abc import Callable
from dataclasses import dataclass

from minicode_agent.models.base import ModelProvider
from minicode_agent.persistence import (
    CheckpointStore,
    NullCheckpointStore,
    NullTraceSink,
    TraceSink,
)
from minicode_agent.runtime.agent import AgentRuntime, ToolExecutor
from minicode_agent.runtime.context import ContextManager
from minicode_agent.runtime.types import AgentConfig


@dataclass(slots=True)
class AgentHarness:
    """Assemble replaceable runtime capabilities in one explicit boundary.

    The harness owns dependency composition while :class:`AgentRuntime` owns the
    model-tool execution loop. Keeping this boundary small makes providers,
    tool registries, policies, and persistence implementations independently
    replaceable for CLI, Web, tests, and future presets.
    """

    model: ModelProvider
    tools: ToolExecutor
    config: AgentConfig
    context: ContextManager | None = None
    trace: TraceSink | None = None
    checkpoint: CheckpointStore | None = None

    def build_runtime(
        self,
        *,
        on_model_delta: Callable[[str, int, str], None] | None = None,
    ) -> AgentRuntime:
        """使用当前 Harness 的能力构建 Runtime。

        可选 Sink 会被空操作实现替代，而不是把 `None` 判断留在 Runtime 内部。`on_model_delta`
        仍是显式回调，因为它属于临时 UI 关注点，而不是持久化 Runtime 状态。
        """
        return AgentRuntime(
            self.model,
            self.tools,
            config=self.config,
            context=self.context or ContextManager(self.config.max_context_tokens),
            trace=self.trace or NullTraceSink(),
            checkpoint=self.checkpoint or NullCheckpointStore(),
            on_model_delta=on_model_delta,
        )
