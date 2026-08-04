"""Manage Web executions while reading shared CLI/Web timeline history."""

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from minicode_agent.models.base import ModelProvider
from minicode_agent.persistence import (
    JsonlTraceSink,
    PersistentRunRecorder,
    SqliteCheckpointStore,
    SqliteRunStore,
    StoredRun,
)
from minicode_agent.runtime import AgentConfig, AgentRuntime, ToolCall
from minicode_agent.security import PermissionLevel, PermissionPolicy, Workspace
from minicode_agent.tools import create_default_registry
from minicode_agent.web.models import ApprovalView, CreateRunRequest, ResumeRunRequest, RunView


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class _PendingApproval:
    view: ApprovalView
    future: asyncio.Future[bool]


@dataclass
class _RunRecord:
    run_id: str
    workspace: Path
    config: AgentConfig
    pending: _PendingApproval | None = None
    task_handle: asyncio.Task[None] | None = None


class _WebApprover:
    def __init__(self, manager: "RunManager", record: _RunRecord) -> None:
        self.manager = manager
        self.record = record

    async def approve(self, call: ToolCall, permission: PermissionLevel) -> bool:
        loop = asyncio.get_running_loop()
        pending = _PendingApproval(
            view=ApprovalView(
                approval_id=uuid4().hex,
                call=call,
                permission=permission,
                created_at=_now(),
            ),
            future=loop.create_future(),
        )
        self.record.pending = pending
        self.manager._append_event(
            self.record,
            "approval_required",
            pending.view.model_dump(mode="json"),
        )
        try:
            approved = await pending.future
        finally:
            self.record.pending = None

        self.manager._append_event(
            self.record,
            "approval_resolved",
            {"approval_id": pending.view.approval_id, "approved": approved},
        )
        return approved


class RunManager:
    """Execute Web runs and project workspace-local persisted history."""

    def __init__(
        self,
        provider_factory: Callable[[], ModelProvider],
        *,
        model_name: str,
        default_workspace: Path | None = None,
    ) -> None:
        self.provider_factory = provider_factory
        self.model_name = model_name
        self.default_workspace = Workspace(default_workspace or Path.cwd()).root
        self._stores: dict[Path, SqliteRunStore] = {
            self.default_workspace: SqliteRunStore(self.default_workspace)
        }
        self._records: dict[str, _RunRecord] = {}

    def list_runs(self) -> list[RunView]:
        stored_runs = {
            run.run_id: run for store in self._stores.values() for run in store.list_runs()
        }
        ordered = sorted(stored_runs.values(), key=lambda item: item.updated_at, reverse=True)
        return [self._view(run) for run in ordered]

    def get_run(self, run_id: str) -> RunView:
        store = self._find_store(run_id)
        run = store.get_run(run_id)
        if run is None:
            raise KeyError(f"run not found: {run_id}")
        return self._view(run)

    def get_events(self, run_id: str) -> list[dict]:
        return self._find_store(run_id).list_events(run_id)

    async def create_run(self, request: CreateRunRequest) -> RunView:
        workspace = Workspace(Path(request.workspace)).root
        config = AgentConfig(
            max_steps=request.max_steps,
            max_context_tokens=request.max_context_tokens,
            max_total_tokens=request.max_total_tokens,
        )
        run_id = uuid4().hex
        store = self._store_for_workspace(workspace)
        store.create_run(
            run_id=run_id,
            source="web",
            task=request.task,
            model_name=self.model_name,
            config=config.model_dump(),
        )
        record = _RunRecord(run_id=run_id, workspace=workspace, config=config)
        self._records[run_id] = record
        self._append_event(record, "run_queued", {"task": request.task})
        record.task_handle = asyncio.create_task(self._execute(record, request.task, resume=False))
        return self.get_run(run_id)

    async def resume_run(self, run_id: str, request: ResumeRunRequest) -> RunView:
        store = self._find_store(run_id)
        stored = store.get_run(run_id)
        if stored is None:
            raise KeyError(f"run not found: {run_id}")
        if stored.source != "web":
            raise ValueError("CLI runs are read-only in the Web Console")
        record = self._records.get(run_id)
        if record is not None and record.task_handle is not None and not record.task_handle.done():
            raise ValueError("run is still active")
        if stored.status == "completed":
            raise ValueError("completed runs cannot be resumed")

        config = AgentConfig(
            max_steps=request.max_steps,
            max_context_tokens=request.max_context_tokens,
            max_total_tokens=request.max_total_tokens,
        )
        store.update_config(run_id, config.model_dump())
        record = _RunRecord(run_id=run_id, workspace=Path(stored.workspace), config=config)
        self._records[run_id] = record
        self._append_event(record, "run_resume_queued", {"max_steps": request.max_steps})
        record.task_handle = asyncio.create_task(self._execute(record, stored.task, resume=True))
        return self.get_run(run_id)

    def resolve_approval(self, run_id: str, approval_id: str, approved: bool) -> RunView:
        stored = self._find_store(run_id).get_run(run_id)
        if stored is None:
            raise KeyError(f"run not found: {run_id}")
        if stored.source != "web":
            raise ValueError("CLI runs cannot be approved from the Web Console")
        record = self._records.get(run_id)
        pending = record.pending if record is not None else None
        if pending is None or pending.view.approval_id != approval_id:
            raise ValueError("approval request is no longer pending")
        if pending.future.done():
            raise ValueError("approval request was already resolved")
        pending.future.set_result(approved)
        return self.get_run(run_id)

    async def subscribe(self, run_id: str, *, after: int = 0) -> AsyncIterator[dict]:
        store = self._find_store(run_id)
        while True:
            events = store.list_events(run_id, after=after)
            for event in events:
                after = int(event["id"])
                yield event
            await asyncio.sleep(0.25)

    async def shutdown(self) -> None:
        active = [
            record.task_handle
            for record in self._records.values()
            if record.task_handle is not None and not record.task_handle.done()
        ]
        for task in active:
            task.cancel()
        if active:
            await asyncio.gather(*active, return_exceptions=True)

    async def _execute(self, record: _RunRecord, task: str, *, resume: bool) -> None:
        self._append_event(record, "run_status", {"status": "running"})
        provider = self.provider_factory()
        store = self._store_for_workspace(record.workspace)
        recorder = PersistentRunRecorder(
            JsonlTraceSink(record.workspace / ".minicode" / "traces.jsonl"),
            store,
        )
        runtime = AgentRuntime(
            provider,
            create_default_registry(
                record.workspace,
                PermissionPolicy(_WebApprover(self, record)),
            ),
            config=record.config,
            trace=recorder,
            checkpoint=SqliteCheckpointStore(record.workspace / ".minicode" / "checkpoints.db"),
            on_model_delta=recorder.on_model_delta,
        )
        try:
            if resume:
                await runtime.resume(record.run_id)
            else:
                await runtime.run(task, run_id=record.run_id)
        except asyncio.CancelledError:
            self._append_event(record, "run_status", {"status": "cancelled"})
            raise
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            self._append_event(record, "web_error", {"error": error})
        finally:
            recorder.flush_model_delta()
            close = getattr(provider, "aclose", None)
            if close is not None:
                await close()

    def _append_event(self, record: _RunRecord, event_type: str, data: dict) -> None:
        self._store_for_workspace(record.workspace).append_event(record.run_id, event_type, data)

    def _store_for_workspace(self, workspace: Path) -> SqliteRunStore:
        root = Workspace(workspace).root
        store = self._stores.get(root)
        if store is None:
            store = SqliteRunStore(root)
            self._stores[root] = store
        return store

    def _find_store(self, run_id: str) -> SqliteRunStore:
        record = self._records.get(run_id)
        if record is not None:
            return self._store_for_workspace(record.workspace)
        for store in self._stores.values():
            if store.get_run(run_id) is not None:
                return store
        raise KeyError(f"run not found: {run_id}")

    def _view(self, run: StoredRun) -> RunView:
        record = self._records.get(run.run_id)
        pending = record.pending.view if record is not None and record.pending is not None else None
        return RunView(
            run_id=run.run_id,
            source=run.source,
            task=run.task,
            workspace=run.workspace,
            model_name=run.model_name,
            status=run.status,
            steps=run.steps,
            input_tokens=run.input_tokens,
            output_tokens=run.output_tokens,
            output=run.output,
            error=run.error,
            created_at=run.created_at,
            updated_at=run.updated_at,
            max_steps=run.max_steps,
            max_context_tokens=run.max_context_tokens,
            max_total_tokens=run.max_total_tokens,
            event_count=run.event_count,
            pending_approval=pending,
        )
