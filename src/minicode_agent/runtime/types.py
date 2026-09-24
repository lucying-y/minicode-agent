"""Runtime、模型和工具之间交换的类型化消息。

这些模型构成 bundle 之间的窄数据契约。保持它们与 Provider 无关，才能让 Fake Provider、
OpenAI-compatible Provider、CLI 和 Web Console 共享同一个 Runtime 实现。
"""

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


class ModelStreamChunk(BaseModel):
    """One text delta or the assembled final response from a streaming provider."""

    delta: str = ""
    response: ModelResponse | None = None


class ToolResult(BaseModel):
    """Structured result returned by a tool executor."""

    content: str
    is_error: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentConfig(BaseModel):
    """单个 Runtime 实例的限制和指令。

    ``max_steps`` 限制模型请求次数，``max_total_tokens`` 限制报告的用量，``max_context_tokens``
    限制历史裁剪后单次请求的上下文大小。这些是应用层限制，不能替代 Provider 配额或操作
    系统安全控制。
    """

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
    CANCELLED = "cancelled"


class RunResult(BaseModel):
    """Final state returned by the runtime."""

    run_id: str
    status: RunStatus
    output: str = ""
    messages: list[Message]
    steps: int
    usage: TokenUsage
    error: str | None = None


class RunCheckpoint(BaseModel):
    """运行最近一致点的可序列化状态。

    Checkpoint 包含继续或展示运行所需的信息，但有意不包含活动进程或待处理审批。这些对象
    属于入口管理器，必须由它们显式重建。
    """

    run_id: str
    task: str
    status: str
    messages: list[Message]
    steps: int
    usage: TokenUsage
    trace_sequence: int
    output: str = ""
    error: str | None = None
