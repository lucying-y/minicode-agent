"""Checkpoint storage for interrupted and limited runs."""

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
    def save(self, checkpoint: RunCheckpoint) -> None:
        del checkpoint

    def load(self, run_id: str) -> RunCheckpoint | None:
        del run_id
        return None


class SqliteCheckpointStore:
    """Store one JSON snapshot per run in SQLite."""

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
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM checkpoints WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return RunCheckpoint.model_validate_json(row[0])
