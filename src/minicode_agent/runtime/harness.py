"""Composable capability bundle for the MiniCode agent runtime."""

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
        """Build a runtime with this harness's capabilities."""
        return AgentRuntime(
            self.model,
            self.tools,
            config=self.config,
            context=self.context or ContextManager(self.config.max_context_tokens),
            trace=self.trace or NullTraceSink(),
            checkpoint=self.checkpoint or NullCheckpointStore(),
            on_model_delta=on_model_delta,
        )
