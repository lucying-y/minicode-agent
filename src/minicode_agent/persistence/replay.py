"""Project a Session Event Log back into a user-facing run state."""

from collections.abc import Iterable, Mapping
from typing import Any

from pydantic import BaseModel, Field

from minicode_agent.runtime.types import Message, TokenUsage, ToolCall


class ReplayState(BaseModel):
    """Deterministic state reconstructed only from ordered session events."""

    run_id: str
    status: str = "unknown"
    messages: list[Message] = Field(default_factory=list)
    steps: int = 0
    usage: TokenUsage = Field(default_factory=TokenUsage)
    output: str = ""
    error: str | None = None
    event_count: int = 0


class SessionReplay:
    """Rebuild conversation state from Run Store or trace-shaped event mappings."""

    _status_by_event = {
        "run_queued": "queued",
        "run_started": "running",
        "run_resumed": "running",
        "run_status": None,
        "user_message": "running",
        "approval_required": "waiting_approval",
        "run_cancel_requested": "cancelling",
        "session_started": "idle",
        "session_waiting_input": "idle",
        "session_limit_reached": "token_limit",
        "session_finished": "completed",
    }

    @classmethod
    def project(cls, events: Iterable[Mapping[str, Any]]) -> ReplayState:
        """Project events in sequence order into a consistent replay state."""
        ordered = list(events)
        if not ordered:
            raise ValueError("cannot replay an empty session event log")
        first = ordered[0]
        run_id = str(first.get("run_id", ""))
        if not run_id:
            raise ValueError("session event is missing run_id")

        messages: list[Message] = []
        usage = TokenUsage()
        status = "unknown"
        steps = 0
        output = ""
        error: str | None = None

        for event in ordered:
            event_type = str(event.get("event_type", ""))
            data = event.get("data") or {}
            if not isinstance(data, Mapping):
                raise ValueError(f"event data must be an object: {event_type}")

            if event_type in {"run_started", "session_started"}:
                config = data.get("config")
                if isinstance(config, Mapping):
                    system_prompt = config.get("system_prompt")
                    if isinstance(system_prompt, str) and not any(
                        message.role == "system" for message in messages
                    ):
                        messages.append(Message(role="system", content=system_prompt))
            elif event_type == "user_message":
                content = data.get("content")
                if isinstance(content, str):
                    messages.append(Message(role="user", content=content))
            elif event_type == "model_response":
                raw_calls = data.get("tool_calls") or []
                calls = [ToolCall.model_validate(call) for call in raw_calls]
                content = data.get("content", "")
                messages.append(Message(role="assistant", content=str(content), tool_calls=calls))
                steps = max(steps, int(data.get("step", steps)))
                raw_usage = data.get("usage") or {}
                if isinstance(raw_usage, Mapping):
                    usage.input_tokens += int(raw_usage.get("input_tokens", 0))
                    usage.output_tokens += int(raw_usage.get("output_tokens", 0))
            elif event_type == "tool_result":
                call = data.get("call") or {}
                result = data.get("result") or {}
                if isinstance(call, Mapping) and isinstance(result, Mapping):
                    messages.append(
                        Message(
                            role="tool",
                            name=str(call.get("name", "")),
                            tool_call_id=str(call.get("id", "")),
                            content=str(result.get("content", "")),
                        )
                    )
            elif event_type == "run_finished" or event_type == "run_cancelled":
                status = str(data.get("status", status))
                steps = int(data.get("steps", steps))
                raw_usage = data.get("usage") or {}
                if isinstance(raw_usage, Mapping):
                    usage = TokenUsage.model_validate(raw_usage)
                output = str(data.get("output", output))
                error_value = data.get("error")
                error = str(error_value) if error_value is not None else None
            elif event_type == "run_status":
                status = str(data.get("status", status))
            elif event_type == "model_error" or event_type == "web_error":
                error_value = data.get("error")
                error = str(error_value) if error_value is not None else error
                status = "failed"

            mapped_status = cls._status_by_event.get(event_type, "")
            if mapped_status:
                status = mapped_status

        return ReplayState(
            run_id=run_id,
            status=status,
            messages=messages,
            steps=steps,
            usage=usage,
            output=output,
            error=error,
            event_count=len(ordered),
        )
