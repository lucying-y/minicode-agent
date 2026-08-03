"""Append-only JSONL execution traces."""

import json
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel


class TraceEvent(BaseModel):
    """One ordered event in an agent run."""

    run_id: str
    sequence: int
    timestamp: str
    event_type: str
    data: dict[str, Any]


class TraceSink(Protocol):
    def record(self, event: TraceEvent) -> None:
        """Persist an event before returning."""
        ...


class NullTraceSink:
    def record(self, event: TraceEvent) -> None:
        del event


class JsonlTraceSink:
    """Append each event as one JSON line."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def record(self, event: TraceEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event.model_dump(mode="json"), ensure_ascii=False) + "\n")

