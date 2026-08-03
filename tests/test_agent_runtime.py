from minicode_agent.models import FakeModelProvider
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
    assert result.output == "done"
    assert result.steps == 1


async def test_runtime_executes_tool_and_returns_observation_to_model() -> None:
    call = ToolCall(id="call-1", name="echo", arguments={"text": "hello"})
    model = FakeModelProvider(
        [
            ModelResponse(tool_calls=[call], usage=TokenUsage(input_tokens=10, output_tokens=2)),
            ModelResponse(content="observed hello", usage=TokenUsage(input_tokens=12, output_tokens=3)),
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
    calls = [ToolCall(id=f"call-{index}", name="echo", arguments={"text": "again"}) for index in range(2)]
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

