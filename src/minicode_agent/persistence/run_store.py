"""Shared SQLite run history for CLI and Web Console timelines."""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Literal

from pydantic import BaseModel

from minicode_agent.persistence.trace import JsonlTraceSink, TraceEvent


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _sqlite_text(value: Any) -> str:
    return str(value).encode("utf-8", errors="replace").decode("utf-8")


def _json_safe(value: Any) -> Any:
    if isinstance(value, str):
        return _sqlite_text(value)
    if isinstance(value, dict):
        return {_sqlite_text(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


class StoredRun(BaseModel):
    """One durable run summary shared by all local entry points."""

    run_id: str
    source: Literal["cli", "web"]
    mode: Literal["task", "chat"]
    task: str
    workspace: str
    model_name: str
    status: str
    steps: int
    input_tokens: int
    output_tokens: int
    output: str
    error: str | None
    created_at: str
    updated_at: str
    max_steps: int
    max_context_tokens: int
    max_total_tokens: int
    event_count: int


class SqliteRunStore:
    """Persist run summaries and ordered events inside one workspace."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.expanduser().resolve()
        self.path = self.workspace / ".minicode" / "runs.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL CHECK (source IN ('cli', 'web')),
                    task TEXT NOT NULL,
                    workspace TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    steps INTEGER NOT NULL DEFAULT 0,
                    input_tokens INTEGER NOT NULL DEFAULT 0,
                    output_tokens INTEGER NOT NULL DEFAULT 0,
                    output TEXT NOT NULL DEFAULT '',
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    event_count INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS events (
                    run_id TEXT NOT NULL,
                    id INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    runtime_sequence INTEGER,
                    data_json TEXT NOT NULL,
                    PRIMARY KEY (run_id, id),
                    FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_runs_updated_at ON runs(updated_at DESC);
                """
            )

    def create_run(
        self,
        *,
        run_id: str,
        source: Literal["cli", "web"],
        task: str,
        model_name: str,
        config: dict[str, Any],
        status: str = "queued",
    ) -> StoredRun:
        timestamp = _now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO runs (
                    run_id, source, task, workspace, model_name, status, config_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO NOTHING
                """,
                (
                    run_id,
                    source,
                    _sqlite_text(task),
                    str(self.workspace),
                    _sqlite_text(model_name),
                    status,
                    json.dumps(_json_safe(config), ensure_ascii=False),
                    timestamp,
                    timestamp,
                ),
            )
        run = self.get_run(run_id)
        if run is None:
            raise RuntimeError(f"unable to create run: {run_id}")
        return run

    def update_config(self, run_id: str, config: dict[str, Any]) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE runs SET config_json = ?, updated_at = ? WHERE run_id = ?",
                (json.dumps(_json_safe(config), ensure_ascii=False), _now(), run_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"run not found: {run_id}")

    def update_task(self, run_id: str, task: str) -> None:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE runs SET task = ?, updated_at = ? WHERE run_id = ?",
                (_sqlite_text(task), _now(), run_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(f"run not found: {run_id}")

    def get_run(self, run_id: str) -> StoredRun | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        return self._run_from_row(row) if row is not None else None

    def list_runs(self) -> list[StoredRun]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM runs ORDER BY updated_at DESC").fetchall()
        return [self._run_from_row(row) for row in rows]

    def append_event(
        self,
        run_id: str,
        event_type: str,
        data: dict[str, Any],
        *,
        runtime_sequence: int | None = None,
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        event_timestamp = timestamp or _now()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT event_count FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"run not found: {run_id}")
            event_id = int(row["event_count"]) + 1
            connection.execute(
                """
                INSERT INTO events (
                    run_id, id, timestamp, event_type, runtime_sequence, data_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    event_id,
                    event_timestamp,
                    event_type,
                    runtime_sequence,
                    json.dumps(_json_safe(data), ensure_ascii=False),
                ),
            )
            self._apply_event(connection, run_id, event_type, data, event_id, event_timestamp)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return {
            "id": event_id,
            "run_id": run_id,
            "timestamp": event_timestamp,
            "event_type": event_type,
            "runtime_sequence": runtime_sequence,
            "data": data,
        }

    def list_events(self, run_id: str, *, after: int = 0) -> list[dict[str, Any]]:
        if self.get_run(run_id) is None:
            raise KeyError(f"run not found: {run_id}")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM events WHERE run_id = ? AND id > ? ORDER BY id",
                (run_id, after),
            ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "run_id": row["run_id"],
                "timestamp": row["timestamp"],
                "event_type": row["event_type"],
                "runtime_sequence": row["runtime_sequence"],
                "data": json.loads(row["data_json"]),
            }
            for row in rows
        ]

    @staticmethod
    def _apply_event(
        connection: sqlite3.Connection,
        run_id: str,
        event_type: str,
        data: dict[str, Any],
        event_id: int,
        timestamp: str,
    ) -> None:
        status: str | None = None
        if event_type in {
            "run_started",
            "run_resumed",
            "approval_resolved",
            "user_message",
        }:
            status = "running"
        elif event_type == "run_queued" or event_type == "run_resume_queued":
            status = "queued"
        elif event_type == "approval_required":
            status = "waiting_approval"
        elif event_type == "run_cancel_requested":
            status = "cancelling"
        elif event_type == "run_status":
            status = str(data["status"])
        elif event_type == "web_error":
            status = "failed"
        elif event_type in {"session_started", "session_waiting_input"}:
            status = "idle"
        elif event_type == "session_finished":
            status = "completed"
        elif event_type == "session_limit_reached":
            status = "token_limit"

        if event_type == "model_response":
            usage = data.get("usage", {})
            connection.execute(
                """
                UPDATE runs SET
                    steps = ?,
                    input_tokens = input_tokens + ?,
                    output_tokens = output_tokens + ?
                WHERE run_id = ?
                """,
                (
                    int(data["step"]),
                    int(usage.get("input_tokens", 0)),
                    int(usage.get("output_tokens", 0)),
                    run_id,
                ),
            )
        elif event_type in {"run_finished", "run_cancelled"}:
            usage = data.get("usage", {})
            connection.execute(
                """
                UPDATE runs SET
                    status = ?, steps = ?, input_tokens = ?, output_tokens = ?,
                    output = ?, error = ?
                WHERE run_id = ?
                """,
                (
                    str(data["status"]),
                    int(data["steps"]),
                    int(usage.get("input_tokens", 0)),
                    int(usage.get("output_tokens", 0)),
                    _sqlite_text(data.get("output", "")),
                    _sqlite_text(data["error"]) if data.get("error") is not None else None,
                    run_id,
                ),
            )
        elif event_type == "web_error":
            connection.execute(
                "UPDATE runs SET error = ? WHERE run_id = ?",
                (
                    _sqlite_text(data["error"]) if data.get("error") is not None else None,
                    run_id,
                ),
            )

        if status is not None:
            connection.execute("UPDATE runs SET status = ? WHERE run_id = ?", (status, run_id))
        if event_type == "run_resume_queued":
            connection.execute("UPDATE runs SET error = NULL WHERE run_id = ?", (run_id,))
        connection.execute(
            "UPDATE runs SET event_count = ?, updated_at = ? WHERE run_id = ?",
            (event_id, timestamp, run_id),
        )

    @staticmethod
    def _run_from_row(row: sqlite3.Row) -> StoredRun:
        config = json.loads(row["config_json"])
        return StoredRun(
            run_id=row["run_id"],
            source=row["source"],
            mode=config.get("mode", "task"),
            task=row["task"],
            workspace=row["workspace"],
            model_name=row["model_name"],
            status=row["status"],
            steps=int(row["steps"]),
            input_tokens=int(row["input_tokens"]),
            output_tokens=int(row["output_tokens"]),
            output=row["output"],
            error=row["error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            max_steps=int(config.get("max_steps", 12)),
            max_context_tokens=int(config.get("max_context_tokens", 32_000)),
            max_total_tokens=int(config.get("max_total_tokens", 100_000)),
            event_count=int(row["event_count"]),
        )


class PersistentRunRecorder:
    """Write durable Runtime events and batch transient model text deltas."""

    def __init__(
        self,
        trace: JsonlTraceSink,
        store: SqliteRunStore,
        *,
        flush_interval_seconds: float = 0.1,
        max_delta_chars: int = 128,
    ) -> None:
        self.trace = trace
        self.store = store
        self.flush_interval_seconds = flush_interval_seconds
        self.max_delta_chars = max_delta_chars
        self._delta_run_id: str | None = None
        self._delta_step = 0
        self._delta_parts: list[str] = []
        self._delta_chars = 0
        self._last_flush = perf_counter()

    def record(self, event: TraceEvent) -> None:
        self.flush_model_delta()
        self.trace.record(event)
        self.store.append_event(
            event.run_id,
            event.event_type,
            event.data,
            runtime_sequence=event.sequence,
            timestamp=event.timestamp,
        )

    def on_model_delta(self, run_id: str, step: int, delta: str) -> None:
        if self._delta_run_id is not None and (
            self._delta_run_id != run_id or self._delta_step != step
        ):
            self.flush_model_delta()
        self._delta_run_id = run_id
        self._delta_step = step
        self._delta_parts.append(delta)
        self._delta_chars += len(delta)
        if (
            self._delta_chars >= self.max_delta_chars
            or perf_counter() - self._last_flush >= self.flush_interval_seconds
        ):
            self.flush_model_delta()

    def flush_model_delta(self) -> None:
        if self._delta_run_id is None or not self._delta_parts:
            return
        self.store.append_event(
            self._delta_run_id,
            "model_output_delta",
            {"step": self._delta_step, "delta": "".join(self._delta_parts)},
        )
        self._delta_run_id = None
        self._delta_step = 0
        self._delta_parts.clear()
        self._delta_chars = 0
        self._last_flush = perf_counter()
