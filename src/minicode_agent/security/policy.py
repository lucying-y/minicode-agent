"""Permission decisions for state-changing tools."""

from enum import StrEnum
from typing import Protocol

from minicode_agent.runtime.types import ToolCall


class PermissionLevel(StrEnum):
    """Risk class attached to a tool."""

    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"


class PermissionDenied(RuntimeError):
    """Raised when a tool call is not authorized."""


class ApprovalHandler(Protocol):
    """Obtain human or policy approval for a state-changing call."""

    async def approve(self, call: ToolCall, permission: PermissionLevel) -> bool:
        """Return whether the call may proceed."""
        ...


class PermissionPolicy:
    """Allow reads and require approval for writes and commands."""

    _blocked_command_fragments = (
        "rm -rf",
        "sudo ",
        "shutdown",
        "reboot",
        "mkfs",
        "git reset --hard",
        "git clean -fd",
        ":(){:|:&};:",
    )

    def __init__(self, approver: ApprovalHandler | None = None) -> None:
        self.approver = approver

    async def authorize(self, call: ToolCall, permission: PermissionLevel) -> None:
        if permission is PermissionLevel.READ:
            return

        if permission is PermissionLevel.EXECUTE:
            command = str(call.arguments.get("command", "")).lower()
            if any(fragment in command for fragment in self._blocked_command_fragments):
                raise PermissionDenied("command matches a blocked high-risk pattern")

        if self.approver is None:
            raise PermissionDenied(f"{permission.value} tool requires explicit approval")

        if not await self.approver.approve(call, permission):
            raise PermissionDenied(f"{permission.value} tool call was rejected")

