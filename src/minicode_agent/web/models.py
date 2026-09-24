"""Web Console API 暴露的数据 Schema。

这些模型构成 HTTP 边界：在用户输入进入 ``RunManager`` 前完成校验，并描述返回给 React
Console 的只读视图。它们有意不包含执行逻辑。
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from minicode_agent.runtime import AgentPreset, ToolCall
from minicode_agent.security import ApprovalMode, PermissionLevel


class CreateRunRequest(BaseModel):
    """一次新仓库任务的配置。

    限制在 API 边界进行约束，避免浏览器仅通过发送很大的 JSON 数值就请求无界 Runtime。
    """

    task: str = Field(min_length=1, max_length=20_000)
    workspace: str = Field(min_length=1)
    max_steps: int = Field(default=12, ge=1, le=100)
    max_context_tokens: int = Field(default=32_000, ge=128, le=1_000_000)
    max_total_tokens: int = Field(default=100_000, ge=1, le=10_000_000)
    approval_mode: ApprovalMode = ApprovalMode.ASK
    preset: AgentPreset = AgentPreset.STANDARD


class ResumeRunRequest(BaseModel):
    """继续已停止运行时应用的限制。"""

    max_steps: int = Field(ge=1, le=100)
    max_context_tokens: int = Field(default=32_000, ge=128, le=1_000_000)
    max_total_tokens: int = Field(default=100_000, ge=1, le=10_000_000)
    approval_mode: ApprovalMode = ApprovalMode.ASK
    preset: AgentPreset = AgentPreset.STANDARD


class ApprovalDecision(BaseModel):
    """用户对一个待处理工具请求的响应。"""

    approval_id: str
    approved: bool


class ApprovalView(BaseModel):
    """Console 中展示的待处理工具审批。"""

    approval_id: str
    call: ToolCall
    permission: PermissionLevel
    created_at: datetime


class RunView(BaseModel):
    """面向用户展示的托管运行当前状态。"""

    run_id: str
    source: Literal["cli", "web"]
    mode: Literal["task", "chat"]
    approval_mode: ApprovalMode
    preset: AgentPreset
    tool_names: list[str]
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
    """供前端使用的小型就绪状态响应。"""

    status: Literal["ok"] = "ok"
    model: str
    default_workspace: str
    platform: Literal["windows", "posix"]
    operating_system: str
    shell: Literal["powershell", "posix"]
    shell_name: str
    shell_version: str | None
