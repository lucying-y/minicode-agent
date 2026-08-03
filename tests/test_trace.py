import json
from pathlib import Path

from minicode_agent.models import FakeModelProvider
from minicode_agent.persistence import JsonlTraceSink
from minicode_agent.runtime import AgentRuntime, ModelResponse
from tests.test_agent_runtime import StubTools


async def test_jsonl_trace_records_ordered_run_events(tmp_path: Path) -> None:
    trace_path = tmp_path / "traces.jsonl"
    runtime = AgentRuntime(
        FakeModelProvider([ModelResponse(content="done")]),
        StubTools(),
        trace=JsonlTraceSink(trace_path),
    )

    result = await runtime.run("finish")

    events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    assert [event["event_type"] for event in events] == [
        "run_started",
        "model_response",
        "run_finished",
    ]
    assert [event["sequence"] for event in events] == [1, 2, 3]
    assert {event["run_id"] for event in events} == {result.run_id}
