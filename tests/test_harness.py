from pathlib import Path

from minicode_agent.models import FakeModelProvider
from minicode_agent.runtime import AgentConfig, AgentHarness, AgentRuntime
from minicode_agent.security import Workspace
from minicode_agent.tools import create_default_registry


def test_harness_builds_runtime_from_replaceable_capabilities(tmp_path: Path) -> None:
    model = FakeModelProvider([])
    tools = create_default_registry(tmp_path)
    config = AgentConfig(max_steps=3, max_context_tokens=512)

    harness = AgentHarness(model=model, tools=tools, config=config)

    runtime = harness.build_runtime()

    assert isinstance(runtime, AgentRuntime)
    assert runtime.model is model
    assert runtime.tools is tools
    assert runtime.config is config
    assert runtime.context.max_tokens == 512


def test_harness_keeps_explicit_context_and_persistence(tmp_path: Path) -> None:
    from minicode_agent.persistence import JsonlTraceSink, SqliteCheckpointStore
    from minicode_agent.runtime import ContextManager

    context = ContextManager(1024)
    trace = JsonlTraceSink(tmp_path / "trace.jsonl")
    checkpoint = SqliteCheckpointStore(tmp_path / "checkpoint.db")
    harness = AgentHarness(
        model=FakeModelProvider([]),
        tools=create_default_registry(Workspace(tmp_path).root),
        config=AgentConfig(),
        context=context,
        trace=trace,
        checkpoint=checkpoint,
    )

    runtime = harness.build_runtime()

    assert runtime.context is context
    assert runtime.trace is trace
    assert runtime.checkpoint is checkpoint
