import asyncio
from pathlib import Path

import httpx

from minicode_agent.models import FakeModelProvider
from minicode_agent.runtime import ModelResponse, ToolCall
from minicode_agent.web import RunManager, create_app


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
    manager = RunManager(lambda: model, model_name="fake-model")
    app = create_app(manager)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        health = await client.get("/api/health")
        assert health.json() == {
            "status": "ok",
            "model": "fake-model",
            "default_workspace": str(Path.cwd()),
        }

        created = await client.post(
            "/api/runs",
            json={"task": "update the value", "workspace": str(tmp_path), "max_steps": 1},
        )
        assert created.status_code == 202
        run_id = created.json()["run_id"]

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
    manager = RunManager(lambda: FakeModelProvider([]), model_name="fake-model")
    app = create_app(manager)
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/runs",
            json={"task": "inspect", "workspace": str(tmp_path / "missing")},
        )

    assert response.status_code == 400
    assert "workspace is not a directory" in response.json()["detail"]
