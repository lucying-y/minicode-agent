"""Bounded shell command tool."""

from pydantic import BaseModel, Field

from minicode_agent.execution import ShellBackend, default_shell
from minicode_agent.runtime.types import ToolResult
from minicode_agent.security import PermissionLevel, Workspace
from minicode_agent.tools.base import Tool


class RunShellInput(BaseModel):
    command: str = Field(min_length=1)
    timeout_seconds: int = Field(default=30, ge=1, le=120)
    max_chars: int = Field(default=12_000, ge=1, le=50_000)


class RunShellTool(Tool[RunShellInput]):
    name = "run_shell"
    permission = PermissionLevel.EXECUTE
    input_model = RunShellInput

    def __init__(self, shell: ShellBackend | None = None) -> None:
        self.shell = shell or default_shell()
        self.description = self.shell.tool_description

    async def run(self, data: RunShellInput, workspace: Workspace) -> ToolResult:
        result = await self.shell.run(
            data.command,
            cwd=workspace.root,
            timeout_seconds=data.timeout_seconds,
            max_chars=data.max_chars,
        )
        return ToolResult(
            content=result.output,
            is_error=result.timed_out or result.exit_code != 0,
            metadata={
                "exit_code": result.exit_code,
                "timed_out": result.timed_out,
                "truncated": result.truncated,
                "shell": self.shell.info.kind,
                "shell_name": self.shell.info.display_name,
            },
        )
