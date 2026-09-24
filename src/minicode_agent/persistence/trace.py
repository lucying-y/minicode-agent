"""追加式 JSONL 执行轨迹。

Trace 是 Runtime 产生的底层诊断流，会在可读的本地文件中保留有序事件载荷；更高层的
Run Store 提供可查询摘要，Replay 则从事件重建状态。
"""

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
    """Runtime 发出事件时使用的最小同步 Sink。"""

    def record(self, event: TraceEvent) -> None:
        """Persist an event before returning."""
        ...


class NullTraceSink:
    def record(self, event: TraceEvent) -> None:
        del event


class JsonlTraceSink:
    """将每个事件追加为一行 JSON。

    每行一个事件使文件便于流式读取，并能在进程中断后保留已写内容。Sink 不负责轮转、脱敏
    或加密数据；调用方应把 trace 文件视为可能包含敏感信息的仓库日志。
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def record(self, event: TraceEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event.model_dump(mode="json"), ensure_ascii=False) + "\n")
