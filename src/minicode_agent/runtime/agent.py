"""Bounded and observable model-tool execution loop."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol, cast
from uuid import uuid4

from minicode_agent.models.base import ModelProvider, StreamingModelProvider
from minicode_agent.persistence import (
    CheckpointStore,
    NullCheckpointStore,
    NullTraceSink,
    TraceEvent,
    TraceSink,
)
from minicode_agent.runtime.context import ContextManager
from minicode_agent.runtime.types import (
    AgentConfig,
    Message,
    ModelResponse,
    RunCheckpoint,
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
        checkpoint: CheckpointStore | None = None,
        on_model_delta: Callable[[str, int, str], None] | None = None,
    ) -> None:
        self.model = model
        self.tools = tools
        self.config = config or AgentConfig()
        self.context = context or ContextManager(self.config.max_context_tokens)
        self.trace = trace or NullTraceSink()
        self.checkpoint = checkpoint or NullCheckpointStore()
        self.on_model_delta = on_model_delta
        self._sequence = 0

    async def run(self, task: str, *, run_id: str | None = None) -> RunResult:
        run_id = run_id or uuid4().hex
        self._sequence = 0
        messages = [
            Message(role="system", content=self.config.system_prompt),
            Message(role="user", content=task),
        ]
        usage = TokenUsage()
        self._emit(run_id, "run_started", {"task": task, "config": self.config.model_dump()})
        self._save_checkpoint(run_id, task, "running", messages, 0, usage)
        return await self._continue(run_id, task, messages, usage, start_step=1)

    def start_session(self, run_id: str, *, task: str = "Interactive CLI session") -> None:
        """Create an idle conversation checkpoint without calling the model."""
        self._sequence = 0
        messages = [Message(role="system", content=self.config.system_prompt)]
        usage = TokenUsage()
        self._emit(
            run_id,
            "session_started",
            {"task": task, "config": self.config.model_dump()},
        )
        self._save_checkpoint(run_id, task, "idle", messages, 0, usage)

    async def continue_conversation(
        self,
        run_id: str,
        content: str,
        *,
        max_steps: int | None = None,
    ) -> RunResult:
        """Append one user turn and keep the same messages, usage, and run identifier."""
        if not content.strip():
            raise ValueError("conversation message cannot be empty")
        checkpoint = self.checkpoint.load(run_id)
        if checkpoint is None:
            raise ValueError(f"checkpoint not found: {run_id}")
        if checkpoint.usage.total_tokens >= self.config.max_total_tokens:
            raise ValueError("session token limit reached; use /clear to start a new session")

        turn_step_limit = checkpoint.steps + (max_steps or self.config.max_steps)
        self._sequence = checkpoint.trace_sequence
        messages = list(checkpoint.messages)
        messages.append(Message(role="user", content=content))
        self._emit(
            run_id,
            "user_message",
            {"content": content, "turn_step_limit": turn_step_limit},
        )
        self._save_checkpoint(
            run_id,
            checkpoint.task,
            "running",
            messages,
            checkpoint.steps,
            checkpoint.usage,
        )
        result = await self._continue(
            run_id,
            checkpoint.task,
            messages,
            checkpoint.usage.model_copy(deep=True),
            start_step=checkpoint.steps + 1,
            step_limit=turn_step_limit,
        )
        token_limit_reached = result.usage.total_tokens >= self.config.max_total_tokens
        self._emit(
            run_id,
            "session_limit_reached" if token_limit_reached else "session_waiting_input",
            {"last_status": result.status.value},
        )
        self._save_checkpoint(
            run_id,
            checkpoint.task,
            RunStatus.TOKEN_LIMIT.value if token_limit_reached else "idle",
            result.messages,
            result.steps,
            result.usage,
            output=result.output,
            error=result.error,
        )
        return result

    def end_session(self, run_id: str, *, reason: str = "quit") -> None:
        """Close an interactive session while preserving its final checkpoint."""
        checkpoint = self.checkpoint.load(run_id)
        if checkpoint is None:
            raise ValueError(f"checkpoint not found: {run_id}")
        self._sequence = checkpoint.trace_sequence
        self._emit(
            run_id,
            "session_finished",
            {
                "reason": reason,
                "steps": checkpoint.steps,
                "usage": checkpoint.usage.model_dump(),
            },
        )
        self._save_checkpoint(
            run_id,
            checkpoint.task,
            RunStatus.COMPLETED.value,
            checkpoint.messages,
            checkpoint.steps,
            checkpoint.usage,
            output=checkpoint.output,
            error=checkpoint.error,
        )

    def cancel(self, run_id: str, *, reason: str = "user_requested") -> RunResult:
        """Stop at the last consistent checkpoint and preserve it for resume."""
        checkpoint = self.checkpoint.load(run_id)
        if checkpoint is None:
            raise ValueError(f"checkpoint not found: {run_id}")
        self._sequence = max(self._sequence, checkpoint.trace_sequence)
        result = RunResult(
            run_id=run_id,
            status=RunStatus.CANCELLED,
            output=checkpoint.output,
            messages=list(checkpoint.messages),
            steps=checkpoint.steps,
            usage=checkpoint.usage.model_copy(deep=True),
            error=None,
        )
        if checkpoint.status == RunStatus.CANCELLED.value:
            return result
        self._emit(
            run_id,
            "run_cancelled",
            {
                "status": RunStatus.CANCELLED.value,
                "reason": reason,
                "steps": checkpoint.steps,
                "usage": checkpoint.usage.model_dump(),
                "output": checkpoint.output,
                "error": None,
            },
        )
        self._save_checkpoint(
            run_id,
            checkpoint.task,
            RunStatus.CANCELLED.value,
            list(checkpoint.messages),
            checkpoint.steps,
            checkpoint.usage,
            output=checkpoint.output,
        )
        return result

    async def resume(self, run_id: str) -> RunResult:
        """Continue a non-completed run from its last consistent checkpoint."""
        checkpoint = self.checkpoint.load(run_id)
        if checkpoint is None:
            raise ValueError(f"checkpoint not found: {run_id}")
        if checkpoint.status == RunStatus.COMPLETED.value:
            raise ValueError(f"run is already completed: {run_id}")

        self._sequence = checkpoint.trace_sequence
        self._emit(
            run_id,
            "run_resumed",
            {"from_status": checkpoint.status, "completed_steps": checkpoint.steps},
        )
        self._save_checkpoint(
            run_id,
            checkpoint.task,
            "running",
            checkpoint.messages,
            checkpoint.steps,
            checkpoint.usage,
        )
        return await self._continue(
            run_id,
            checkpoint.task,
            list(checkpoint.messages),
            checkpoint.usage.model_copy(deep=True),
            start_step=checkpoint.steps + 1,
        )

    async def _continue(
        self,
        run_id: str,
        task: str,
        messages: list[Message],
        usage: TokenUsage,
        *,
        start_step: int,
        step_limit: int | None = None,
    ) -> RunResult:
        resolved_step_limit = step_limit or self.config.max_steps
        for step in range(start_step, resolved_step_limit + 1):
            try:
                model_messages = self.context.prepare(messages)
                response = await self._complete_model(run_id, step, model_messages)
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                self._emit(run_id, "model_error", {"step": step, "error": error})
                return self._finish(
                    run_id, task, RunStatus.FAILED, messages, step, usage, error=error
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
                    task,
                    RunStatus.TOKEN_LIMIT,
                    messages,
                    step,
                    usage,
                    output=response.content,
                )

            if not response.tool_calls:
                return self._finish(
                    run_id,
                    task,
                    RunStatus.COMPLETED,
                    messages,
                    step,
                    usage,
                    output=response.content,
                )

            for call in response.tool_calls:
                self._emit(
                    run_id,
                    "tool_requested",
                    {"step": step, "call": call.model_dump(mode="json")},
                )
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
                        task,
                        RunStatus.TOOL_ERROR,
                        messages,
                        step,
                        usage,
                        output=result.content,
                    )

            self._save_checkpoint(run_id, task, "running", messages, step, usage)

        return self._finish(
            run_id,
            task,
            RunStatus.STEP_LIMIT,
            messages,
            max(start_step - 1, resolved_step_limit),
            usage,
        )

    async def _execute_tool(self, call: ToolCall) -> ToolResult:
        try:
            return await self.tools.execute(call)
        except Exception as exc:
            return ToolResult(content=f"{type(exc).__name__}: {exc}", is_error=True)

    async def _complete_model(
        self,
        run_id: str,
        step: int,
        messages: list[Message],
    ) -> ModelResponse:
        if not getattr(self.model, "supports_streaming", False):
            return await self.model.complete(messages, self.tools.schemas())

        provider = cast(StreamingModelProvider, self.model)
        response: ModelResponse | None = None
        async for chunk in provider.stream_complete(messages, self.tools.schemas()):
            if chunk.delta and self.on_model_delta is not None:
                self.on_model_delta(run_id, step, chunk.delta)
            if chunk.response is not None:
                response = chunk.response
        if response is None:
            raise RuntimeError("streaming provider ended without a final response")
        return response

    def _finish(
        self,
        run_id: str,
        task: str,
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
                "output": output,
                "error": error,
            },
        )
        self._save_checkpoint(
            run_id,
            task,
            status.value,
            messages,
            steps,
            usage,
            output=output,
            error=error,
        )
        return result

    def _save_checkpoint(
        self,
        run_id: str,
        task: str,
        status: str,
        messages: list[Message],
        steps: int,
        usage: TokenUsage,
        *,
        output: str = "",
        error: str | None = None,
    ) -> None:
        self.checkpoint.save(
            RunCheckpoint(
                run_id=run_id,
                task=task,
                status=status,
                messages=messages,
                steps=steps,
                usage=usage,
                trace_sequence=self._sequence,
                output=output,
                error=error,
            )
        )

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
