import pytest

from minicode_agent.persistence import SessionReplay


def test_replay_reconstructs_messages_status_and_usage() -> None:
    events = [
        {
            "run_id": "run-1",
            "event_type": "run_started",
            "data": {"config": {"system_prompt": "be precise"}},
        },
        {"run_id": "run-1", "event_type": "user_message", "data": {"content": "inspect"}},
        {
            "run_id": "run-1",
            "event_type": "model_response",
            "data": {
                "step": 1,
                "content": "I will inspect it.",
                "tool_calls": [
                    {"id": "call-1", "name": "read_file", "arguments": {"path": "a.py"}}
                ],
                "usage": {"input_tokens": 10, "output_tokens": 4},
            },
        },
        {
            "run_id": "run-1",
            "event_type": "tool_result",
            "data": {
                "call": {"id": "call-1", "name": "read_file"},
                "result": {"content": "value = 1", "is_error": False},
            },
        },
        {
            "run_id": "run-1",
            "event_type": "run_finished",
            "data": {
                "status": "completed",
                "steps": 2,
                "usage": {"input_tokens": 12, "output_tokens": 7},
                "output": "done",
                "error": None,
            },
        },
    ]

    state = SessionReplay.project(events)

    assert state.run_id == "run-1"
    assert state.status == "completed"
    assert state.steps == 2
    assert state.usage.total_tokens == 19
    assert state.output == "done"
    assert [(message.role, message.content) for message in state.messages] == [
        ("system", "be precise"),
        ("user", "inspect"),
        ("assistant", "I will inspect it."),
        ("tool", "value = 1"),
    ]
    assert state.messages[2].tool_calls[0].name == "read_file"


def test_replay_uses_latest_terminal_error_and_rejects_invalid_logs() -> None:
    state = SessionReplay.project(
        [
            {"run_id": "run-2", "event_type": "run_started", "data": {}},
            {
                "run_id": "run-2",
                "event_type": "model_error",
                "data": {"error": "provider failed"},
            },
        ]
    )

    assert state.status == "failed"
    assert state.error == "provider failed"
    with pytest.raises(ValueError, match="empty"):
        SessionReplay.project([])
    with pytest.raises(ValueError, match="missing run_id"):
        SessionReplay.project([{"event_type": "run_started", "data": {}}])
