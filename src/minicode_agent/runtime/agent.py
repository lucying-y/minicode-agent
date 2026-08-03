"""Bounded and observable model-tool execution loop."""

from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from minicode_agent.models.base import ModelProvider
from minicode_agent.persistence import NullTraceSink, TraceEvent, TraceSink
from minicode_agent.runtime.context import ContextManager
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
        context: ContextManager | None = None,
        trace: TraceSink | None = None,
    ) -> None:
        self.model = model
        self.tools = tools
        self.config = config or AgentConfig()
        self.context = context or ContextManager(self.config.max_context_tokens)
        self.trace = trace or NullTraceSink()
        self._sequence = 0

    async def run(self, task: str) -> RunResult:
        run_id = uuid4().hex
        self._sequence = 0
        messages = [
            Message(role="system", content=self.config.system_prompt),
            Message(role="user", content=task),
        ]
        usage = TokenUsage()
        self._emit(run_id, "run_started", {"task": task, "config": self.config.model_dump()})

        for step in range(1, self.config.max_steps + 1):
            try:
                model_messages = self.context.prepare(messages)
                response = await self.model.complete(model_messages, self.tools.schemas())
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                self._emit(run_id, "model_error", {"step": step, "error": error})
                return self._finish(
                    run_id, RunStatus.FAILED, messages, step, usage, error=error
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
            self._emit(
                run_id,
                "model_response",
                {
                    "step": step,
                    "content": response.content,
                    "tool_calls": [call.model_dump(mode="json") for call in response.tool_calls],
                    "usage": response.usage.model_dump(),
                    "context_messages": len(model_messages),
                },
            )

            if usage.total_tokens > self.config.max_total_tokens:
                return self._finish(
                    run_id,
                    RunStatus.TOKEN_LIMIT,
                    messages,
                    step,
                    usage,
                    output=response.content,
                )

            if not response.tool_calls:
                return self._finish(
                    run_id,
                    RunStatus.COMPLETED,
                    messages,
                    step,
                    usage,
                    output=response.content,
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
                self._emit(
                    run_id,
                    "tool_result",
                    {
                        "step": step,
                        "call": call.model_dump(mode="json"),
                        "result": result.model_dump(mode="json"),
                    },
                )
                if result.is_error and self.config.stop_on_tool_error:
                    return self._finish(
                        run_id,
                        RunStatus.TOOL_ERROR,
                        messages,
                        step,
                        usage,
                        output=result.content,
                    )

        return self._finish(
            run_id,
            RunStatus.STEP_LIMIT,
            messages,
            self.config.max_steps,
            usage,
        )

    async def _execute_tool(self, call: ToolCall) -> ToolResult:
        try:
            return await self.tools.execute(call)
        except Exception as exc:
            return ToolResult(content=f"{type(exc).__name__}: {exc}", is_error=True)

    def _finish(
        self,
        run_id: str,
        status: RunStatus,
        messages: list[Message],
        steps: int,
        usage: TokenUsage,
        *,
        output: str = "",
        error: str | None = None,
    ) -> RunResult:
        result = RunResult(
            run_id=run_id,
            status=status,
            output=output,
            messages=messages,
            steps=steps,
            usage=usage,
            error=error,
        )
        self._emit(
            run_id,
            "run_finished",
            {
                "status": status.value,
                "steps": steps,
                "usage": usage.model_dump(),
                "error": error,
            },
        )
        return result

    def _emit(self, run_id: str, event_type: str, data: dict) -> None:
        self._sequence += 1
        self.trace.record(
            TraceEvent(
                run_id=run_id,
                sequence=self._sequence,
                timestamp=datetime.now(UTC).isoformat(),
                event_type=event_type,
                data=data,
            )
        )
