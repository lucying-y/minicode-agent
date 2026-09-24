"""Extension points around structured tool execution.

Hooks are intentionally surface-neutral.  They can feed a CLI recorder, a Web
event stream, metrics, or an audit sink without making tools depend on any of
those applications.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from minicode_agent.runtime.types import ToolCall, ToolResult
from minicode_agent.security import PermissionLevel


class ToolHook(Protocol):
    """Observe a tool call before authorization and after execution.

    A hook may transform the result in `after_execute`, but it should avoid
    performing unrelated side effects that could make retries non-deterministic.
    """

    async def before_execute(self, call: ToolCall, permission: PermissionLevel) -> None:
        """Run before argument validation and permission authorization."""
        ...

    async def after_execute(
        self,
        call: ToolCall,
        permission: PermissionLevel,
        result: ToolResult,
    ) -> ToolResult:
        """Observe or transform the structured result."""
        ...


@dataclass(frozen=True, slots=True)
class ToolAuditEvent:
    """Surface-neutral audit record emitted around one tool call."""

    phase: Literal["requested", "completed"]
    call: ToolCall
    permission: PermissionLevel
    result: ToolResult | None = None


class AuditHook:
    """Send structured tool lifecycle records to a caller-owned sink."""

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
