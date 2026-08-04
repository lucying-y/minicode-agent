"""FastAPI application for the local Web Console."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from minicode_agent.web.manager import RunManager
from minicode_agent.web.models import (
    ApprovalDecision,
    CreateRunRequest,
    HealthView,
    ResumeRunRequest,
    RunView,
)


def create_app(manager: RunManager, *, static_dir: Path | None = None) -> FastAPI:
    """Create an API app around one process-local Run Manager."""

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        await manager.shutdown()

    app = FastAPI(title="MiniCode Agent Web API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health", response_model=HealthView)
    async def health() -> HealthView:
        return HealthView(
            model=manager.model_name,
            default_workspace=str(manager.default_workspace),
            platform=manager.shell.info.platform,
            operating_system=manager.shell.info.operating_system,
            shell=manager.shell.info.kind,
            shell_name=manager.shell.info.name,
            shell_version=manager.shell.info.version,
        )

    @app.get("/api/runs", response_model=list[RunView])
    async def list_runs() -> list[RunView]:
        return manager.list_runs()

    @app.post("/api/runs", response_model=RunView, status_code=202)
    async def create_run(request: CreateRunRequest) -> RunView:
        try:
            return await manager.create_run(request)
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/runs/{run_id}", response_model=RunView)
    async def get_run(run_id: str) -> RunView:
        try:
            return manager.get_run(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/runs/{run_id}/events/history")
    async def event_history(run_id: str) -> list[dict]:
        try:
            return manager.get_events(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/runs/{run_id}/events")
    async def stream_events(
        run_id: str,
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    ) -> StreamingResponse:
        try:
            after = int(last_event_id or 0)
            manager.get_run(run_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid Last-Event-ID") from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        async def event_stream() -> AsyncIterator[str]:
            yield ": connected\n\n"
            async for event in manager.subscribe(run_id, after=after):
                payload = json.dumps(event, ensure_ascii=False)
                yield f"id: {event['id']}\ndata: {payload}\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post("/api/runs/{run_id}/approval", response_model=RunView)
    async def resolve_approval(run_id: str, decision: ApprovalDecision) -> RunView:
        try:
            return manager.resolve_approval(run_id, decision.approval_id, decision.approved)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/runs/{run_id}/resume", response_model=RunView, status_code=202)
    async def resume_run(run_id: str, request: ResumeRunRequest) -> RunView:
        try:
            return await manager.resume_run(run_id, request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/runs/{run_id}/cancel", response_model=RunView)
    async def cancel_run(run_id: str) -> RunView:
        try:
            return await manager.cancel_run(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    resolved_static = static_dir.resolve() if static_dir is not None else None
    if resolved_static is not None and (resolved_static / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=resolved_static / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def serve_console(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API route not found")
        if resolved_static is None or not (resolved_static / "index.html").is_file():
            raise HTTPException(
                status_code=503,
                detail="Web Console is not built. Run `npm ci && npm run build` in web/.",
            )
        candidate = (resolved_static / path).resolve()
        if candidate.is_relative_to(resolved_static) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(resolved_static / "index.html")

    return app
