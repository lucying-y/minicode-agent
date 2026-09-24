"""结构化工具执行过程中的扩展点。

Hook 有意不依赖特定界面。它们可以向 CLI Recorder、Web 事件流、指标或审计 Sink 提供数据，
而无需让工具依赖这些应用。
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from minicode_agent.runtime.types import ToolCall, ToolResult
from minicode_agent.security import PermissionLevel


class ToolHook(Protocol):
    """在授权前和执行后观察工具调用。

    Hook 可以在 `after_execute` 中转换结果，但应避免执行无关副作用，以免重试行为变得不确定。
    """

    async def before_execute(self, call: ToolCall, permission: PermissionLevel) -> None:
        """在参数校验和权限授权之前执行。"""
        ...

    async def after_execute(
        self,
        call: ToolCall,
        permission: PermissionLevel,
        result: ToolResult,
    ) -> ToolResult:
        """观察或转换结构化结果。"""
        ...


@dataclass(frozen=True, slots=True)
class ToolAuditEvent:
    """一次工具调用生命周期中产生的、与界面无关的审计记录。"""

    phase: Literal["requested", "completed"]
    call: ToolCall
    permission: PermissionLevel
    result: ToolResult | None = None


class AuditHook:
    """将结构化工具生命周期记录发送给调用方提供的 Sink。"""

    def __init__(self, sink: Callable[[ToolAuditEvent], None]) -> None:
        self.sink = sink

    async def before_execute(self, call: ToolCall, permission: PermissionLevel) -> None:
        self.sink(ToolAuditEvent("requested", call, permission))

    async def after_execute(
        self,
        call: ToolCall,
        permission: PermissionLevel,
        result: ToolResult,
    ) -> ToolResult:
        self.sink(ToolAuditEvent("completed", call, permission, result))
        return result
