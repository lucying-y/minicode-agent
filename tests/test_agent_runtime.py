from pathlib import Path

from minicode_agent.models import FakeModelProvider
from minicode_agent.persistence import SqliteCheckpointStore
from minicode_agent.runtime import (
    AgentConfig,
    AgentRuntime,
    ModelResponse,
    RunStatus,
    TokenUsage,
    ToolCall,
    ToolResult,
    ToolSchema,
)


class StubTools:
    def __init__(self) -> None:
        self.calls: list[ToolCall] = []

    def schemas(self) -> list[ToolSchema]:
        return [
            ToolSchema(
                name="echo",
                description="Return the provided text.",
                parameters={
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
            )
        ]

    async def execute(self, call: ToolCall) -> ToolResult:
        self.calls.append(call)
        return ToolResult(content=str(call.arguments["text"]))


async def test_runtime_completes_without_tool_call() -> None:
    model = FakeModelProvider([ModelResponse(content="done")])
    runtime = AgentRuntime(model, StubTools())

    result = await runtime.run("finish the task")

    assert result.status is RunStatus.COMPLETED
    assert result.run_id
    assert result.output == "done"
    assert result.steps == 1


async def test_runtime_accepts_preallocated_run_id() -> None:
    runtime = AgentRuntime(FakeModelProvider([ModelResponse(content="done")]), StubTools())

    result = await runtime.run("finish the task", run_id="web-run-1")

    assert result.run_id == "web-run-1"


async def test_runtime_executes_tool_and_returns_observation_to_model() -> None:
    call = ToolCall(id="call-1", name="echo", arguments={"text": "hello"})
    model = FakeModelProvider(
        [
            ModelResponse(tool_calls=[call], usage=TokenUsage(input_tokens=10, output_tokens=2)),
            ModelResponse(
                content="observed hello",
                usage=TokenUsage(input_tokens=12, output_tokens=3),
            ),
        ]
    )
    tools = StubTools()
    runtime = AgentRuntime(model, tools)

    result = await runtime.run("use the echo tool")

    assert result.status is RunStatus.COMPLETED
    assert result.steps == 2
    assert result.usage.total_tokens == 27
    assert tools.calls == [call]
    second_request_messages, _ = model.requests[1]
    assert second_request_messages[-1].role == "tool"
    assert second_request_messages[-1].content == "hello"
    assert second_request_messages[-1].tool_call_id == "call-1"


async def test_runtime_stops_at_step_limit() -> None:
    calls = [
        ToolCall(id=f"call-{index}", name="echo", arguments={"text": "again"})
        for index in range(2)
    ]
    model = FakeModelProvider([ModelResponse(tool_calls=[call]) for call in calls])
    runtime = AgentRuntime(model, StubTools(), AgentConfig(max_steps=2))

    result = await runtime.run("keep using tools")

    assert result.status is RunStatus.STEP_LIMIT
    assert result.steps == 2


async def test_runtime_stops_before_tools_when_token_limit_is_exceeded() -> None:
    call = ToolCall(id="call-1", name="echo", arguments={"text": "should not run"})
    model = FakeModelProvider(
        [ModelResponse(tool_calls=[call], usage=TokenUsage(input_tokens=8, output_tokens=4))]
    )
    tools = StubTools()
    runtime = AgentRuntime(model, tools, AgentConfig(max_total_tokens=10))

    result = await runtime.run("expensive request")

    assert result.status is RunStatus.TOKEN_LIMIT
    assert tools.calls == []


async def test_runtime_reports_model_errors() -> None:
    model = FakeModelProvider([])
    runtime = AgentRuntime(model, StubTools())

    result = await runtime.run("there is no fake response")

    assert result.status is RunStatus.FAILED
    assert "no scripted response" in str(result.error)


async def test_runtime_forwards_streaming_model_deltas() -> None:
    deltas: list[tuple[str, int, str]] = []
    model = FakeModelProvider(
        [ModelResponse(content="streamed response")],
        streaming=True,
        stream_chunk_size=5,
    )
    runtime = AgentRuntime(
        model,
        StubTools(),
        on_model_delta=lambda run_id, step, delta: deltas.append((run_id, step, delta)),
    )

    result = await runtime.run("stream the answer", run_id="stream-run")

    assert result.status is RunStatus.COMPLETED
    assert "".join(delta for _, _, delta in deltas) == "streamed response"
    assert {(run_id, step) for run_id, step, _ in deltas} == {("stream-run", 1)}


async def test_runtime_preserves_context_across_interactive_turns(tmp_path: Path) -> None:
    checkpoint_store = SqliteCheckpointStore(tmp_path / "checkpoints.db")
    model = FakeModelProvider(
        [
            ModelResponse(
                content="first answer",
                usage=TokenUsage(input_tokens=5, output_tokens=2),
            ),
            ModelResponse(
                content="second answer",
                usage=TokenUsage(input_tokens=7, output_tokens=3),
            ),
        ]
    )
    runtime = AgentRuntime(model, StubTools(), checkpoint=checkpoint_store)
    runtime.start_session("chat-run")

    first = await runtime.continue_conversation("chat-run", "first question", max_steps=2)
    second = await runtime.continue_conversation("chat-run", "follow up", max_steps=2)

    assert first.steps == 1
    assert second.steps == 2
    assert second.usage.total_tokens == 17
    second_request, _ = model.requests[1]
    assert [(message.role, message.content) for message in second_request[-3:]] == [
        ("user", "first question"),
        ("assistant", "first answer"),
        ("user", "follow up"),
    ]
    checkpoint = checkpoint_store.load("chat-run")
    assert checkpoint is not None
    assert checkpoint.status == "idle"
    assert checkpoint.steps == 2

    runtime.end_session("chat-run")
    closed = checkpoint_store.load("chat-run")
    assert closed is not None
    assert closed.status == RunStatus.COMPLETED.value


async def test_interactive_session_marks_exact_token_limit(tmp_path: Path) -> None:
    checkpoint_store = SqliteCheckpointStore(tmp_path / "checkpoints.db")
    runtime = AgentRuntime(
        FakeModelProvider(
            [
                ModelResponse(
                    content="done",
                    usage=TokenUsage(input_tokens=3, output_tokens=2),
                )
            ]
        ),
        StubTools(),
        AgentConfig(max_total_tokens=5),
        checkpoint=checkpoint_store,
    )
    runtime.start_session("limited-chat")

    result = await runtime.continue_conversation("limited-chat", "answer once")

    assert result.status is RunStatus.COMPLETED
    checkpoint = checkpoint_store.load("limited-chat")
    assert checkpoint is not None
    assert checkpoint.status == RunStatus.TOKEN_LIMIT.value


async def test_runtime_cancellation_preserves_resumable_checkpoint(tmp_path: Path) -> None:
    checkpoint_store = SqliteCheckpointStore(tmp_path / "checkpoints.db")
    runtime = AgentRuntime(
        FakeModelProvider([]),
        StubTools(),
        checkpoint=checkpoint_store,
    )
    runtime.start_session("cancel-run", task="cancel safely")

    result = runtime.cancel("cancel-run", reason="user_requested")
    repeated = runtime.cancel("cancel-run", reason="duplicate")

    assert result.status is RunStatus.CANCELLED
    assert repeated.status is RunStatus.CANCELLED
    checkpoint = checkpoint_store.load("cancel-run")
    assert checkpoint is not None
    assert checkpoint.status == RunStatus.CANCELLED.value
    assert checkpoint.task == "cancel safely"
