"""Agent runtime public API."""

from typing import TYPE_CHECKING, Any

from minicode_agent.runtime.context import ContextManager
from minicode_agent.runtime.types import (
    AgentConfig,
    Message,
    ModelResponse,
    ModelStreamChunk,
    RunCheckpoint,
    RunResult,
    RunStatus,
    TokenUsage,
    ToolCall,
    ToolResult,
    ToolSchema,
)

if TYPE_CHECKING:
    from minicode_agent.runtime.agent import AgentRuntime, ToolExecutor

__all__ = [
    "AgentConfig",
    "AgentRuntime",
    "ContextManager",
    "Message",
    "ModelResponse",
    "ModelStreamChunk",
    "RunCheckpoint",
    "RunResult",
    "RunStatus",
    "TokenUsage",
    "ToolCall",
    "ToolExecutor",
    "ToolResult",
    "ToolSchema",
]


def __getattr__(name: str) -> Any:
    if name in {"AgentRuntime", "ToolExecutor"}:
        from minicode_agent.runtime.agent import AgentRuntime, ToolExecutor

        return {"AgentRuntime": AgentRuntime, "ToolExecutor": ToolExecutor}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
