"""Manage background Agent Runtime executions for the Web Console."""

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from minicode_agent.models.base import ModelProvider
from minicode_agent.persistence import JsonlTraceSink, SqliteCheckpointStore, TraceEvent, TraceSink
from minicode_agent.runtime import AgentConfig, AgentRuntime, RunResult, ToolCall
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
    task: str
    workspace: Path
    config: AgentConfig
    status: str = "queued"
    steps: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    output: str = ""
    error: str | None = None
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)
    events: list[dict[str, Any]] = field(default_factory=list)
    subscribers: set[asyncio.Queue[dict[str, Any]]] = field(default_factory=set)
    pending: _PendingApproval | None = None
    task_handle: asyncio.Task[None] | None = None
    event_sequence: int = 0


class _ForwardingTraceSink:
    def __init__(self, primary: TraceSink, callback: Callable[[TraceEvent], None]) -> None:
        self.primary = primary
        self.callback = callback

    def record(self, event: TraceEvent) -> None:
        self.primary.record(event)
        self.callback(event)


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
        self.record.status = "waiting_approval"
        self.manager._publish(
            self.record,
            "approval_required",
            pending.view.model_dump(mode="json"),
        )
        try:
            approved = await pending.future
        finally:
            self.record.pending = None

        self.record.status = "running"
        self.manager._publish(
            self.record,
            "approval_resolved",
            {"approval_id": pending.view.approval_id, "approved": approved},
        )
        return approved


class RunManager:
    """Own in-memory run state while durable Runtime data stays in each workspace."""

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
        self._records: dict[str, _RunRecord] = {}

    def list_runs(self) -> list[RunView]:
        records = sorted(self._records.values(), key=lambda item: item.created_at, reverse=True)
        return [self._view(record) for record in records]

    def get_run(self, run_id: str) -> RunView:
        return self._view(self._get_record(run_id))

    def get_events(self, run_id: str) -> list[dict[str, Any]]:
        return list(self._get_record(run_id).events)

    async def create_run(self, request: CreateRunRequest) -> RunView:
        workspace = Workspace(Path(request.workspace)).root
        record = _RunRecord(
            run_id=uuid4().hex,
            task=request.task,
            workspace=workspace,
            config=AgentConfig(
                max_steps=request.max_steps,
                max_context_tokens=request.max_context_tokens,
                max_total_tokens=request.max_total_tokens,
            ),
        )
        self._records[record.run_id] = record
        self._publish(record, "run_queued", {"task": record.task})
        record.task_handle = asyncio.create_task(self._execute(record, resume=False))
        return self._view(record)

    async def resume_run(self, run_id: str, request: ResumeRunRequest) -> RunView:
        record = self._get_record(run_id)
        if record.task_handle is not None and not record.task_handle.done():
            raise ValueError("run is still active")
        if record.status == "completed":
            raise ValueError("completed runs cannot be resumed")

        record.config = AgentConfig(
            max_steps=request.max_steps,
            max_context_tokens=request.max_context_tokens,
            max_total_tokens=request.max_total_tokens,
        )
        record.status = "queued"
        record.error = None
        self._publish(record, "run_resume_queued", {"max_steps": request.max_steps})
        record.task_handle = asyncio.create_task(self._execute(record, resume=True))
        return self._view(record)

    def resolve_approval(self, run_id: str, approval_id: str, approved: bool) -> RunView:
        record = self._get_record(run_id)
        pending = record.pending
        if pending is None or pending.view.approval_id != approval_id:
            raise ValueError("approval request is no longer pending")
        if pending.future.done():
            raise ValueError("approval request was already resolved")
        pending.future.set_result(approved)
        return self._view(record)

    async def subscribe(self, run_id: str, *, after: int = 0) -> AsyncIterator[dict[str, Any]]:
        record = self._get_record(run_id)
        for event in record.events:
            if int(event["id"]) > after:
                yield event

        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=256)
        record.subscribers.add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            record.subscribers.discard(queue)

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

    async def _execute(self, record: _RunRecord, *, resume: bool) -> None:
        record.status = "running"
        self._publish(record, "run_status", {"status": record.status})
        provider = self.provider_factory()
        approver = _WebApprover(self, record)
        trace = _ForwardingTraceSink(
            JsonlTraceSink(record.workspace / ".minicode" / "traces.jsonl"),
            lambda event: self._record_runtime_event(record, event),
        )
        runtime = AgentRuntime(
            provider,
            create_default_registry(record.workspace, PermissionPolicy(approver)),
            config=record.config,
            trace=trace,
            checkpoint=SqliteCheckpointStore(record.workspace / ".minicode" / "checkpoints.db"),
            on_model_delta=lambda _run_id, step, delta: self._publish(
                record,
                "model_output_delta",
                {"step": step, "delta": delta},
            ),
        )
        try:
            result = (
                await runtime.resume(record.run_id)
                if resume
                else await runtime.run(record.task, run_id=record.run_id)
            )
            self._apply_result(record, result)
        except asyncio.CancelledError:
            record.status = "cancelled"
            self._publish(record, "run_status", {"status": record.status})
            raise
        except Exception as exc:
            record.status = "failed"
            record.error = f"{type(exc).__name__}: {exc}"
            self._publish(record, "web_error", {"error": record.error})
        finally:
            close = getattr(provider, "aclose", None)
            if close is not None:
                await close()

    def _record_runtime_event(self, record: _RunRecord, event: TraceEvent) -> None:
        data = event.data
        if event.event_type == "model_response":
            record.steps = int(data["step"])
            usage = data.get("usage", {})
            record.input_tokens += int(usage.get("input_tokens", 0))
            record.output_tokens += int(usage.get("output_tokens", 0))
        elif event.event_type == "run_finished":
            record.status = str(data["status"])
            record.steps = int(data["steps"])
            usage = data.get("usage", {})
            record.input_tokens = int(usage.get("input_tokens", 0))
            record.output_tokens = int(usage.get("output_tokens", 0))
            record.error = data.get("error")
        self._publish(
            record,
            event.event_type,
            data,
            runtime_sequence=event.sequence,
            timestamp=event.timestamp,
        )

    @staticmethod
    def _apply_result(record: _RunRecord, result: RunResult) -> None:
        record.status = result.status.value
        record.steps = result.steps
        record.input_tokens = result.usage.input_tokens
        record.output_tokens = result.usage.output_tokens
        record.output = result.output
        record.error = result.error
        record.updated_at = _now()

    def _publish(
        self,
        record: _RunRecord,
        event_type: str,
        data: dict[str, Any],
        *,
        runtime_sequence: int | None = None,
        timestamp: str | None = None,
    ) -> None:
        record.event_sequence += 1
        record.updated_at = _now()
        event = {
            "id": record.event_sequence,
            "run_id": record.run_id,
            "timestamp": timestamp or record.updated_at.isoformat(),
            "event_type": event_type,
            "runtime_sequence": runtime_sequence,
            "data": data,
        }
        record.events.append(event)
        for queue in record.subscribers:
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(event)

    def _get_record(self, run_id: str) -> _RunRecord:
        try:
            return self._records[run_id]
        except KeyError as exc:
            raise KeyError(f"run not found: {run_id}") from exc

    @staticmethod
    def _view(record: _RunRecord) -> RunView:
        return RunView(
            run_id=record.run_id,
            task=record.task,
            workspace=str(record.workspace),
            status=record.status,
            steps=record.steps,
            input_tokens=record.input_tokens,
            output_tokens=record.output_tokens,
            output=record.output,
            error=record.error,
            created_at=record.created_at,
            updated_at=record.updated_at,
            max_steps=record.config.max_steps,
            max_context_tokens=record.config.max_context_tokens,
            max_total_tokens=record.config.max_total_tokens,
            event_count=len(record.events),
            pending_approval=record.pending.view if record.pending is not None else None,
        )
