"""Schemas exposed by the Web Console API."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from minicode_agent.runtime import ToolCall
from minicode_agent.security import ApprovalMode, PermissionLevel


class CreateRunRequest(BaseModel):
    """Configuration for one new repository task."""

    task: str = Field(min_length=1, max_length=20_000)
    workspace: str = Field(min_length=1)
    max_steps: int = Field(default=12, ge=1, le=100)
    max_context_tokens: int = Field(default=32_000, ge=128, le=1_000_000)
    max_total_tokens: int = Field(default=100_000, ge=1, le=10_000_000)
    approval_mode: ApprovalMode = ApprovalMode.ASK


class ResumeRunRequest(BaseModel):
    """Limits applied when continuing a stopped run."""

    max_steps: int = Field(ge=1, le=100)
    max_context_tokens: int = Field(default=32_000, ge=128, le=1_000_000)
    max_total_tokens: int = Field(default=100_000, ge=1, le=10_000_000)
    approval_mode: ApprovalMode = ApprovalMode.ASK


class ApprovalDecision(BaseModel):
    """Human response to one pending tool request."""

    approval_id: str
    approved: bool


class ApprovalView(BaseModel):
    """Pending tool approval shown in the Console."""

    approval_id: str
    call: ToolCall
    permission: PermissionLevel
    created_at: datetime


class RunView(BaseModel):
    """Current user-facing state of a managed run."""

    run_id: str
    source: Literal["cli", "web"]
    mode: Literal["task", "chat"]
    approval_mode: ApprovalMode
    task: str
    workspace: str
    model_name: str
    status: str
    steps: int
    input_tokens: int
    output_tokens: int
    output: str
    error: str | None
    created_at: datetime
    updated_at: datetime
    max_steps: int
    max_context_tokens: int
    max_total_tokens: int
    event_count: int
    pending_approval: ApprovalView | None


class HealthView(BaseModel):
    """Small readiness response used by the frontend."""

    status: Literal["ok"] = "ok"
    model: str
    default_workspace: str
    platform: Literal["windows", "posix"]
    operating_system: str
    shell: Literal["powershell", "posix"]
    shell_name: str
    shell_version: str | None
