import pytest

from minicode_agent.runtime import Message, ToolCall
from minicode_agent.runtime.context import ContextManager


def test_context_keeps_full_history_when_under_budget() -> None:
    messages = [Message(role="system", content="system"), Message(role="user", content="task")]
    manager = ContextManager(max_tokens=128)

    assert manager.prepare(messages) == messages


def test_context_rejects_unusable_budget() -> None:
    with pytest.raises(ValueError, match="at least 128"):
        ContextManager(max_tokens=127)


def test_context_drops_old_complete_blocks_and_keeps_latest_block() -> None:
    messages = [
        Message(role="system", content="system"),
        Message(role="user", content="task"),
        Message(
            role="assistant",
            content="old decision " * 80,
            tool_calls=[ToolCall(id="old", name="read_file", arguments={"path": "old.py"})],
        ),
        Message(role="tool", tool_call_id="old", name="read_file", content="old output " * 80),
        Message(
            role="assistant",
            content="latest decision",
            tool_calls=[ToolCall(id="new", name="read_file", arguments={"path": "new.py"})],
        ),
        Message(role="tool", tool_call_id="new", name="read_file", content="latest output"),
    ]
    manager = ContextManager(max_tokens=180)

    prepared = manager.prepare(messages)

    assert prepared[0:2] == messages[0:2]
    assert any("omitted" in message.content for message in prepared)
    assert prepared[-2:] == messages[-2:]
    assert all(message.tool_call_id != "old" for message in prepared)


def test_context_keeps_latest_interactive_user_turn() -> None:
    messages = [
        Message(role="system", content="system"),
        Message(role="user", content="initial task"),
        Message(role="assistant", content="x" * 1000),
        Message(role="user", content="latest follow-up"),
    ]

    prepared = ContextManager(128).prepare(messages)

    assert prepared[0:2] == messages[0:2]
    assert prepared[-1] == messages[-1]
    assert messages[2] not in prepared
