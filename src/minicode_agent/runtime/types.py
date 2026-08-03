"""Typed messages exchanged by the runtime, models, and tools."""

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    """A structured request from the model to a named tool."""

    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolSchema(BaseModel):
    """JSON Schema description exposed to a model."""

    name: str
    description: str
    parameters: dict[str, Any]


class Message(BaseModel):
    """Provider-neutral conversation message."""

    role: Literal["system", "user", "assistant", "tool"]
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None


class TokenUsage(BaseModel):
    """Token counts reported by a model provider."""

    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class ModelResponse(BaseModel):
    """Provider-neutral model response."""

    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    usage: TokenUsage = Field(default_factory=TokenUsage)


class ToolResult(BaseModel):
    """Structured result returned by a tool executor."""

    content: str
    is_error: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentConfig(BaseModel):
    """Limits and instructions for a single runtime instance."""

    system_prompt: str = (
        "You are a coding agent working inside one repository. "
        "Inspect before editing, make focused changes, and verify your work."
    )
    max_steps: int = Field(default=12, ge=1)
    max_total_tokens: int = Field(default=100_000, ge=1)
    max_context_tokens: int = Field(default=32_000, ge=128)
    stop_on_tool_error: bool = False


class RunStatus(StrEnum):
    """Terminal state of an agent run."""

    COMPLETED = "completed"
    STEP_LIMIT = "step_limit"
    TOKEN_LIMIT = "token_limit"
    TOOL_ERROR = "tool_error"
    FAILED = "failed"


class RunResult(BaseModel):
    """Final state returned by the runtime."""

    run_id: str
    status: RunStatus
    output: str = ""
    messages: list[Message]
    steps: int
    usage: TokenUsage
    error: str | None = None
