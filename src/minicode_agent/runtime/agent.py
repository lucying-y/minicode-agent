"""Bounded model-tool execution loop."""

from typing import Protocol

from minicode_agent.models.base import ModelProvider
from minicode_agent.runtime.types import (
    AgentConfig,
    Message,
    RunResult,
    RunStatus,
    TokenUsage,
    ToolCall,
    ToolResult,
    ToolSchema,
)


class ToolExecutor(Protocol):
    """Expose tool schemas and execute structured calls."""

    def schemas(self) -> list[ToolSchema]:
        """Return schemas available during this run."""
        ...

    async def execute(self, call: ToolCall) -> ToolResult:
        """Execute a tool call."""
        ...


class AgentRuntime:
    """Run a model and tool executor until completion or a configured limit."""

    def __init__(
        self,
        model: ModelProvider,
        tools: ToolExecutor,
        config: AgentConfig | None = None,
    ) -> None:
        self.model = model
        self.tools = tools
        self.config = config or AgentConfig()

    async def run(self, task: str) -> RunResult:
        messages = [
            Message(role="system", content=self.config.system_prompt),
            Message(role="user", content=task),
        ]
        usage = TokenUsage()

        for step in range(1, self.config.max_steps + 1):
            try:
                response = await self.model.complete(messages, self.tools.schemas())
            except Exception as exc:
                return RunResult(
                    status=RunStatus.FAILED,
                    messages=messages,
                    steps=step,
                    usage=usage,
                    error=f"{type(exc).__name__}: {exc}",
                )

            usage.input_tokens += response.usage.input_tokens
            usage.output_tokens += response.usage.output_tokens
            messages.append(
                Message(
                    role="assistant",
                    content=response.content,
                    tool_calls=response.tool_calls,
                )
            )

            if usage.total_tokens > self.config.max_total_tokens:
                return RunResult(
                    status=RunStatus.TOKEN_LIMIT,
                    output=response.content,
                    messages=messages,
                    steps=step,
                    usage=usage,
                )

            if not response.tool_calls:
                return RunResult(
                    status=RunStatus.COMPLETED,
                    output=response.content,
                    messages=messages,
                    steps=step,
                    usage=usage,
                )

            for call in response.tool_calls:
                result = await self._execute_tool(call)
                messages.append(
                    Message(
                        role="tool",
                        name=call.name,
                        tool_call_id=call.id,
                        content=result.content,
                    )
                )
                if result.is_error and self.config.stop_on_tool_error:
                    return RunResult(
                        status=RunStatus.TOOL_ERROR,
                        output=result.content,
                        messages=messages,
                        steps=step,
                        usage=usage,
                    )

        return RunResult(
            status=RunStatus.STEP_LIMIT,
            messages=messages,
            steps=self.config.max_steps,
            usage=usage,
        )

    async def _execute_tool(self, call: ToolCall) -> ToolResult:
        try:
            return await self.tools.execute(call)
        except Exception as exc:
            return ToolResult(content=f"{type(exc).__name__}: {exc}", is_error=True)

