import asyncio
from pathlib import Path

import httpx

from minicode_agent.models import FakeModelProvider
from minicode_agent.persistence import SqliteCheckpointStore, SqliteRunStore
from minicode_agent.runtime import Message, ModelResponse, ToolCall, ToolSchema
from minicode_agent.web import RunManager, create_app
from minicode_agent.web.models import CreateRunRequest


async def _wait_for_status(
    manager: RunManager,
    run_id: str,
    expected: str,
) -> None:
    for _ in range(200):
        if manager.get_run(run_id).status == expected:
            return
        await asyncio.sleep(0.005)
    raise AssertionError(f"run did not reach {expected}: {manager.get_run(run_id).status}")


async def test_web_run_approval_events_and_resume(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("value = 1\n", encoding="utf-8")
    model = FakeModelProvider(
        [
            ModelResponse(
                tool_calls=[
                    ToolCall(
                        id="edit-1",
                        name="edit_file",
                        arguments={
                            "path": "app.py",
                            "old_text": "value = 1",
                            "new_text": "value = 2",
                        },
                    )
                ]
            ),
            ModelResponse(content="change verified"),
        ]
    )
    manager = RunManager(lambda: model, model_name="fake-model", default_workspace=tmp_path)
    app = create_app(manager)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        health = await client.get("/api/health")
        health_data = health.json()
        assert health_data["status"] == "ok"
        assert health_data["model"] == "fake-model"
        assert health_data["default_workspace"] == str(tmp_path)
        assert health_data["platform"] in {"windows", "posix"}
        assert health_data["shell"] in {"powershell", "posix"}
        assert health_data["shell_name"]

        created = await client.post(
            "/api/runs",
            json={"task": "update the value", "workspace": str(tmp_path), "max_steps": 1},
        )
        assert created.status_code == 202
        run_id = created.json()["run_id"]
        assert created.json()["source"] == "web"
        assert created.json()["mode"] == "task"
        assert created.json()["model_name"] == "fake-model"

        await _wait_for_status(manager, run_id, "waiting_approval")
        pending = manager.get_run(run_id).pending_approval
        assert pending is not None
        assert pending.call.name == "edit_file"

        approved = await client.post(
            f"/api/runs/{run_id}/approval",
            json={"approval_id": pending.approval_id, "approved": True},
        )
        assert approved.status_code == 200
        await _wait_for_status(manager, run_id, "step_limit")
        assert target.read_text(encoding="utf-8") == "value = 2\n"

        resumed = await client.post(
            f"/api/runs/{run_id}/resume",
            json={"max_steps": 2},
        )
        assert resumed.status_code == 202
        await _wait_for_status(manager, run_id, "completed")

        detail = (await client.get(f"/api/runs/{run_id}")).json()
        assert detail["output"] == "change verified"
        assert detail["steps"] == 2
        assert detail["event_count"] > 0

        events = (await client.get(f"/api/runs/{run_id}/events/history")).json()
        event_types = [event["event_type"] for event in events]
        assert "approval_required" in event_types
        assert "approval_resolved" in event_types
        assert "run_resumed" in event_types
        assert event_types[-1] == "run_finished"

    await manager.shutdown()


async def test_web_rejects_missing_workspace(tmp_path: Path) -> None:
    manager = RunManager(
        lambda: FakeModelProvider([]),
        model_name="fake-model",
        default_workspace=tmp_path,
    )
    app = create_app(manager)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/runs",
            json={"task": "inspect", "workspace": str(tmp_path / "missing")},
        )

    assert response.status_code == 400
    assert "workspace is not a directory" in response.json()["detail"]
    await manager.shutdown()


async def test_web_publishes_streaming_model_output(tmp_path: Path) -> None:
    model = FakeModelProvider(
        [ModelResponse(content="streamed web response")],
        streaming=True,
        stream_chunk_size=4,
    )
    manager = RunManager(
        lambda: model,
        model_name="streaming-fake",
        default_workspace=tmp_path,
    )
    app = create_app(manager)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        health = (await client.get("/api/health")).json()
        assert health["default_workspace"] == str(tmp_path)
        created = await client.post(
            "/api/runs",
            json={"task": "stream", "workspace": str(tmp_path)},
        )
        run_id = created.json()["run_id"]
        await _wait_for_status(manager, run_id, "completed")

        events = (await client.get(f"/api/runs/{run_id}/events/history")).json()
        deltas = [
            event["data"]["delta"]
            for event in events
            if event["event_type"] == "model_output_delta"
        ]
        assert "".join(deltas) == "streamed web response"
        assert events[-2]["event_type"] == "model_response"
        assert events[-1]["event_type"] == "run_finished"
        first_request, _ = model.requests[0]
        assert "Runtime environment:" in first_request[0].content
        assert str(tmp_path) in first_request[0].content

    await manager.shutdown()


async def test_web_discovers_external_cli_run_and_streams_its_events(tmp_path: Path) -> None:
    manager = RunManager(
        lambda: FakeModelProvider([]),
        model_name="web-model",
        default_workspace=tmp_path,
    )
    external_store = SqliteRunStore(tmp_path)
    external_store.create_run(
        run_id="cli-run",
        source="cli",
        task="inspect from the terminal",
        model_name="cli-model",
        config={"max_steps": 8, "max_context_tokens": 16_000, "max_total_tokens": 50_000},
    )
    external_store.append_event("cli-run", "run_queued", {"task": "inspect from the terminal"})

    listed = manager.list_runs()
    assert len(listed) == 1
    assert listed[0].source == "cli"
    assert listed[0].mode == "task"
    assert listed[0].model_name == "cli-model"

    subscription = manager.subscribe("cli-run", after=1)
    pending_event = asyncio.create_task(anext(subscription))
    await asyncio.sleep(0)
    external_store.append_event("cli-run", "run_started", {"task": "inspect from the terminal"})

    event = await asyncio.wait_for(pending_event, timeout=1)
    assert event["id"] == 2
    assert event["event_type"] == "run_started"
    await subscription.aclose()

    app = create_app(manager)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resume = await client.post("/api/runs/cli-run/resume", json={"max_steps": 12})
        approval = await client.post(
            "/api/runs/cli-run/approval",
            json={"approval_id": "terminal-only", "approved": True},
        )
        cancel = await client.post("/api/runs/cli-run/cancel")

    assert resume.status_code == 409
    assert "read-only" in resume.json()["detail"]
    assert approval.status_code == 409
    assert "cannot be approved" in approval.json()["detail"]
    assert cancel.status_code == 409
    assert "cannot be cancelled" in cancel.json()["detail"]
    await manager.shutdown()


class BlockingModel:
    supports_streaming = False

    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolSchema],
    ) -> ModelResponse:
        del messages, tools
        self.started.set()
        await asyncio.Event().wait()
        raise AssertionError("blocking model should be cancelled")


async def test_web_cancels_model_request_and_resumes_checkpoint(tmp_path: Path) -> None:
    blocking_model = BlockingModel()
    resumed_model = FakeModelProvider([ModelResponse(content="resumed after cancellation")])
    providers = iter([blocking_model, resumed_model])
    manager = RunManager(
        lambda: next(providers),
        model_name="cancel-test-model",
        default_workspace=tmp_path,
    )
    app = create_app(manager)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/api/runs",
            json={"task": "block until cancelled", "workspace": str(tmp_path)},
        )
        run_id = created.json()["run_id"]
        await asyncio.wait_for(blocking_model.started.wait(), timeout=1)

        cancelled = await client.post(f"/api/runs/{run_id}/cancel")

        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"
        checkpoint = SqliteCheckpointStore(
            tmp_path / ".minicode" / "checkpoints.db"
        ).load(run_id)
        assert checkpoint is not None
        assert checkpoint.status == "cancelled"

        events = (await client.get(f"/api/runs/{run_id}/events/history")).json()
        event_types = [event["event_type"] for event in events]
        assert "run_cancel_requested" in event_types
        assert event_types[-1] == "run_cancelled"

        resumed = await client.post(
            f"/api/runs/{run_id}/resume",
            json={"max_steps": 12},
        )
        assert resumed.status_code == 202
        await _wait_for_status(manager, run_id, "completed")
        assert manager.get_run(run_id).output == "resumed after cancellation"

        repeated = await client.post(f"/api/runs/{run_id}/cancel")
        assert repeated.status_code == 409
        assert "not active" in repeated.json()["detail"]

    await manager.shutdown()


async def test_web_cancels_pending_approval(tmp_path: Path) -> None:
    model = FakeModelProvider(
        [
            ModelResponse(
                tool_calls=[
                    ToolCall(
                        id="write-1",
                        name="edit_file",
                        arguments={"path": "new.py", "old_text": "", "new_text": "value = 1\n"},
                    )
                ]
            )
        ]
    )
    manager = RunManager(lambda: model, model_name="fake-model", default_workspace=tmp_path)
    app = create_app(manager)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/api/runs",
            json={"task": "wait for approval", "workspace": str(tmp_path)},
        )
        run_id = created.json()["run_id"]
        await _wait_for_status(manager, run_id, "waiting_approval")
        approval_id = manager.get_run(run_id).pending_approval.approval_id

        cancelled = await client.post(f"/api/runs/{run_id}/cancel")
        stale_approval = await client.post(
            f"/api/runs/{run_id}/approval",
            json={"approval_id": approval_id, "approved": True},
        )

        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"
        assert cancelled.json()["pending_approval"] is None
        assert stale_approval.status_code == 409
        assert not (tmp_path / "new.py").exists()

    await manager.shutdown()


async def test_web_cancels_queued_run_before_execution_starts(tmp_path: Path) -> None:
    manager = RunManager(
        lambda: FakeModelProvider([ModelResponse(content="should not run")]),
        model_name="fake-model",
        default_workspace=tmp_path,
    )

    created = await manager.create_run(
        CreateRunRequest(task="cancel while queued", workspace=str(tmp_path))
    )
    cancelled = await manager.cancel_run(created.run_id)

    assert cancelled.status == "cancelled"
    checkpoint = SqliteCheckpointStore(
        tmp_path / ".minicode" / "checkpoints.db"
    ).load(created.run_id)
    assert checkpoint is not None
    assert checkpoint.status == "cancelled"
    assert [message.role for message in checkpoint.messages] == ["system", "user"]
    assert "Runtime environment:" in checkpoint.messages[0].content
    assert checkpoint.messages[1].content == "cancel while queued"

    await manager.shutdown()
