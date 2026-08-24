"""Permission decisions for state-changing tools."""

from enum import StrEnum
from typing import Protocol

from minicode_agent.runtime.types import ToolCall


class PermissionLevel(StrEnum):
    """Risk class attached to a tool."""

    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"


class ApprovalMode(StrEnum):
    """How a run handles otherwise permitted state-changing tools."""

    ASK = "ask"
    AUTO = "auto"
    READ_ONLY = "read_only"


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
        "format-volume",
        "clear-disk",
        "initialize-disk",
        "diskpart",
        "stop-computer",
        "restart-computer",
        "clear-recyclebin",
        "bcdedit",
        "-encodedcommand",
        "-encodedarguments",
        "invoke-expression",
    )

    @classmethod
    def _blocked_command(cls, command: str) -> bool:
        normalized = " ".join(command.casefold().split())
        if any(fragment in normalized for fragment in cls._blocked_command_fragments):
            return True
        tokens = [word.strip(";&|()") for word in normalized.replace("/", " /").split()]
        remove_commands = {"rm", "ri", "remove-item"}
        recurse_options = {"-r", "-recurse"}
        force_options = {"-f", "-fo", "-force"}
        combined_options = {"-rf", "-fr"}
        if remove_commands.intersection(tokens) and (
            combined_options.intersection(tokens)
            or (recurse_options.intersection(tokens) and force_options.intersection(tokens))
        ):
            return True
        if {"del", "erase", "rd", "rmdir"}.intersection(tokens) and "/s" in tokens:
            return True
        return "start-process" in normalized and "-verb runas" in normalized

    def __init__(
        self,
        approver: ApprovalHandler | None = None,
        mode: ApprovalMode = ApprovalMode.ASK,
    ) -> None:
        self.approver = approver
        self.mode = mode

    async def authorize(self, call: ToolCall, permission: PermissionLevel) -> None:
        if permission is PermissionLevel.READ:
            return

        if permission is PermissionLevel.EXECUTE:
            command = str(call.arguments.get("command", ""))
            if self._blocked_command(command):
                raise PermissionDenied("command matches a blocked high-risk pattern")

        if self.mode is ApprovalMode.READ_ONLY:
            raise PermissionDenied("run is read-only; state-changing tools are disabled")
        if self.mode is ApprovalMode.AUTO:
            return

        if self.approver is None:
            raise PermissionDenied(f"{permission.value} tool requires explicit approval")

        if not await self.approver.approve(call, permission):
            raise PermissionDenied(f"{permission.value} tool call was rejected")
