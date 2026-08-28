"""Extension points around structured tool execution."""

from typing import Protocol

from minicode_agent.runtime.types import ToolCall, ToolResult
from minicode_agent.security import PermissionLevel


class ToolHook(Protocol):
    """Observe a tool call before authorization and after execution."""

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
