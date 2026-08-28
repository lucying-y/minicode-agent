"""Append-only JSONL execution traces."""

import json
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel


class SessionEventType(StrEnum):
    """Canonical event names in the append-only Session Event Log."""

    RUN_QUEUED = "run_queued"
    RUN_STARTED = "run_started"
    RUN_STATUS = "run_status"
    RUN_RESUME_QUEUED = "run_resume_queued"
    RUN_RESUMED = "run_resumed"
    RUN_FINISHED = "run_finished"
    RUN_CANCEL_REQUESTED = "run_cancel_requested"
    RUN_CANCELLED = "run_cancelled"
    SESSION_STARTED = "session_started"
    SESSION_WAITING_INPUT = "session_waiting_input"
    SESSION_LIMIT_REACHED = "session_limit_reached"
    SESSION_FINISHED = "session_finished"
    USER_MESSAGE = "user_message"
    MODEL_REQUEST = "model_request"
    MODEL_OUTPUT_DELTA = "model_output_delta"
    MODEL_RESPONSE = "model_response"
    MODEL_ERROR = "model_error"
    TOOL_REQUESTED = "tool_requested"
    TOOL_RESULT = "tool_result"
    APPROVAL_REQUIRED = "approval_required"
    APPROVAL_RESOLVED = "approval_resolved"
    CONTEXT_COMPACTED = "context_compacted"
    WORKSPACE_CHANGES = "workspace_changes"
    TEST_RESULT = "test_result"
    WEB_ERROR = "web_error"


class TraceEvent(BaseModel):
    """One ordered event in an agent run."""

    run_id: str
    sequence: int
    timestamp: str
    event_type: SessionEventType
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
