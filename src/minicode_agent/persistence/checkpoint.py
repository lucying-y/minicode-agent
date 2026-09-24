"""Checkpoint storage for interrupted and limited runs.

Checkpoints are snapshots of the last state at which Runtime can safely resume.
They are deliberately separate from the append-only event log: a snapshot is
optimized for loading one run, while events are optimized for history and
replay.
"""

import sqlite3
from pathlib import Path
from typing import Protocol

from minicode_agent.runtime.types import RunCheckpoint


class CheckpointStore(Protocol):
    """Persist the last internally consistent state of each run."""

    def save(self, checkpoint: RunCheckpoint) -> None:
        """Insert or replace one run checkpoint."""
        ...

    def load(self, run_id: str) -> RunCheckpoint | None:
        """Load a run checkpoint when present."""
        ...


class NullCheckpointStore:
    """No-op implementation for callers that only need one-shot execution."""

    def save(self, checkpoint: RunCheckpoint) -> None:
        del checkpoint

    def load(self, run_id: str) -> RunCheckpoint | None:
        del run_id
        return None


class SqliteCheckpointStore:
    """Store one JSON snapshot per run in SQLite.

    The primary key makes save idempotent: each completed Runtime boundary
    replaces the previous snapshot, and a resume reads exactly one payload.
    SQLite WAL mode allows the CLI and Web process to inspect the same workspace
    database with less reader/writer contention.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS checkpoints (
                    run_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def save(self, checkpoint: RunCheckpoint) -> None:
        """Atomically replace the latest snapshot for a run."""
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO checkpoints (run_id, payload, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(run_id) DO UPDATE SET
                    payload = excluded.payload,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (checkpoint.run_id, checkpoint.model_dump_json()),
            )

    def load(self, run_id: str) -> RunCheckpoint | None:
        """Load and validate one snapshot, returning `None` when absent."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM checkpoints WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return RunCheckpoint.model_validate_json(row[0])
