import json
from pathlib import Path

import pytest

from minicode_agent.models import FakeModelProvider
from minicode_agent.persistence import JsonlTraceSink, SqliteCheckpointStore
from minicode_agent.runtime import (
    AgentConfig,
    AgentRuntime,
    Message,
    ModelResponse,
    RunCheckpoint,
    RunStatus,
    TokenUsage,
    ToolCall,
)
from tests.test_agent_runtime import StubTools


def test_sqlite_checkpoint_round_trip(tmp_path: Path) -> None:
    store = SqliteCheckpointStore(tmp_path / "checkpoints.db")
    checkpoint = RunCheckpoint(
        run_id="run-1",
        task="inspect",
        status="running",
        messages=[Message(role="user", content="inspect")],
        steps=2,
        usage=TokenUsage(input_tokens=10, output_tokens=5),
        trace_sequence=7,
    )

    store.save(checkpoint)

    assert store.load("run-1") == checkpoint
    assert store.load("missing") is None


async def test_runtime_resumes_limited_run_with_same_id_and_trace_sequence(tmp_path: Path) -> None:
    store = SqliteCheckpointStore(tmp_path / "checkpoints.db")
    trace_path = tmp_path / "traces.jsonl"
    first_model = FakeModelProvider(
        [
            ModelResponse(
                tool_calls=[
                    ToolCall(id="call-1", name="echo", arguments={"text": "checkpointed"})
                ],
                usage=TokenUsage(input_tokens=5, output_tokens=2),
            )
        ]
    )
    first_runtime = AgentRuntime(
        first_model,
        StubTools(),
        AgentConfig(max_steps=1),
        trace=JsonlTraceSink(trace_path),
        checkpoint=store,
    )

    limited = await first_runtime.run("use a tool and continue later")

    assert limited.status is RunStatus.STEP_LIMIT
    saved = store.load(limited.run_id)
    assert saved is not None
    assert saved.messages[-1].content == "checkpointed"

    second_runtime = AgentRuntime(
        FakeModelProvider([ModelResponse(content="resumed and complete")]),
        StubTools(),
        AgentConfig(max_steps=3),
        trace=JsonlTraceSink(trace_path),
        checkpoint=store,
    )
    completed = await second_runtime.resume(limited.run_id)

    assert completed.status is RunStatus.COMPLETED
    assert completed.run_id == limited.run_id
    assert completed.steps == 2
    assert completed.usage.total_tokens == 7
    final_checkpoint = store.load(limited.run_id)
    assert final_checkpoint is not None
    assert final_checkpoint.status == RunStatus.COMPLETED.value
    events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))
    assert any(event["event_type"] == "run_resumed" for event in events)

    with pytest.raises(ValueError, match="already completed"):
        await second_runtime.resume(limited.run_id)

