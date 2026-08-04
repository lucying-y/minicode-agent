from pathlib import Path

from minicode_agent.persistence import (
    JsonlTraceSink,
    PersistentRunRecorder,
    SqliteRunStore,
)
from minicode_agent.persistence.trace import TraceEvent


def _create_run(store: SqliteRunStore, run_id: str = "run-1") -> None:
    store.create_run(
        run_id=run_id,
        source="cli",
        task="inspect the repository",
        model_name="test-model",
        config={"max_steps": 4, "max_context_tokens": 8_000, "max_total_tokens": 20_000},
    )


def test_run_store_projects_ordered_events_into_summary(tmp_path: Path) -> None:
    store = SqliteRunStore(tmp_path)
    _create_run(store)

    first = store.append_event("run-1", "run_started", {"task": "inspect the repository"})
    second = store.append_event(
        "run-1",
        "model_response",
        {"step": 1, "usage": {"input_tokens": 12, "output_tokens": 3}},
    )
    store.append_event(
        "run-1",
        "run_finished",
        {
            "status": "completed",
            "steps": 1,
            "usage": {"input_tokens": 12, "output_tokens": 3},
            "output": "done",
            "error": None,
        },
    )

    assert first["id"] == 1
    assert second["id"] == 2
    assert [event["id"] for event in store.list_events("run-1", after=1)] == [2, 3]
    run = store.get_run("run-1")
    assert run is not None
    assert run.status == "completed"
    assert run.steps == 1
    assert run.input_tokens == 12
    assert run.output_tokens == 3
    assert run.output == "done"
    assert run.event_count == 3


def test_separate_store_instances_share_new_runs_and_events(tmp_path: Path) -> None:
    writer = SqliteRunStore(tmp_path)
    reader = SqliteRunStore(tmp_path)
    _create_run(writer, "external-run")
    writer.append_event("external-run", "run_queued", {"task": "inspect the repository"})

    assert [run.run_id for run in reader.list_runs()] == ["external-run"]
    assert reader.list_events("external-run")[0]["event_type"] == "run_queued"


def test_run_store_projects_chat_mode_and_idle_status(tmp_path: Path) -> None:
    store = SqliteRunStore(tmp_path)
    store.create_run(
        run_id="chat-run",
        source="cli",
        task="Interactive CLI session",
        model_name="test-model",
        config={"mode": "chat", "max_steps": 12},
        status="idle",
    )
    store.append_event("chat-run", "session_started", {"task": "Interactive CLI session"})
    store.update_task("chat-run", "inspect the repository")

    run = store.get_run("chat-run")
    assert run is not None
    assert run.mode == "chat"
    assert run.status == "idle"
    assert run.task == "inspect the repository"


def test_recorder_batches_model_deltas_and_preserves_jsonl_trace(tmp_path: Path) -> None:
    store = SqliteRunStore(tmp_path)
    _create_run(store)
    trace_path = tmp_path / ".minicode" / "traces.jsonl"
    recorder = PersistentRunRecorder(
        JsonlTraceSink(trace_path),
        store,
        flush_interval_seconds=60,
        max_delta_chars=5,
    )

    recorder.on_model_delta("run-1", 1, "ab")
    recorder.on_model_delta("run-1", 1, "cde")
    recorder.on_model_delta("run-1", 1, "fg")
    recorder.record(
        TraceEvent(
            run_id="run-1",
            sequence=1,
            timestamp="2026-08-04T00:00:00+00:00",
            event_type="run_started",
            data={"task": "inspect the repository"},
        )
    )

    events = store.list_events("run-1")
    assert [event["event_type"] for event in events] == [
        "model_output_delta",
        "model_output_delta",
        "run_started",
    ]
    assert events[0]["data"]["delta"] == "abcde"
    assert events[1]["data"]["delta"] == "fg"
    assert trace_path.read_text(encoding="utf-8").count("\n") == 1
