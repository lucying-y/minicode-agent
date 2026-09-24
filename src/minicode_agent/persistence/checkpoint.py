"""中断或受限运行的 Checkpoint 存储。

Checkpoint 是 Runtime 可以安全恢复的最近状态快照。它与追加式事件日志有意分离：快照
针对单次运行的快速加载，事件则针对历史记录和 Replay。
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
    """供只需要单次执行的调用方使用的空操作实现。"""

    def save(self, checkpoint: RunCheckpoint) -> None:
        del checkpoint

    def load(self, run_id: str) -> RunCheckpoint | None:
        del run_id
        return None


class SqliteCheckpointStore:
    """在 SQLite 中为每个运行保存一个 JSON 快照。

    主键使保存操作具备幂等性：每个完成的 Runtime 边界都会替换之前的快照，而恢复时只需
    读取一个载荷。SQLite WAL 模式降低 CLI 与 Web 进程检查同一工作区数据库时的读写竞争。
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
        """原子替换某次运行的最新快照。"""
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
        """加载并校验一份快照；不存在时返回 `None`。"""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM checkpoints WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return RunCheckpoint.model_validate_json(row[0])
