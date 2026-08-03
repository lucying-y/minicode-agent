"""Bounded shell command tool."""

import asyncio

from pydantic import BaseModel, Field

from minicode_agent.runtime.types import ToolResult
from minicode_agent.security import PermissionLevel, Workspace
from minicode_agent.tools.base import Tool


class RunShellInput(BaseModel):
    command: str = Field(min_length=1)
    timeout_seconds: int = Field(default=30, ge=1, le=120)
    max_chars: int = Field(default=12_000, ge=1, le=50_000)


class RunShellTool(Tool[RunShellInput]):
    name = "run_shell"
    description = "Run one shell command in the workspace with a timeout and bounded output."
    permission = PermissionLevel.EXECUTE
    input_model = RunShellInput

    async def run(self, data: RunShellInput, workspace: Workspace) -> ToolResult:
        process = await asyncio.create_subprocess_shell(
            data.command,
            cwd=workspace.root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        try:
            output, _ = await asyncio.wait_for(process.communicate(), timeout=data.timeout_seconds)
        except TimeoutError:
            process.kill()
            await process.communicate()
            return ToolResult(
                content=f"command timed out after {data.timeout_seconds}s",
                is_error=True,
                metadata={"exit_code": None, "timed_out": True},
            )

        content = output.decode("utf-8", errors="replace")
        truncated = len(content) > data.max_chars
        if truncated:
            content = content[: data.max_chars] + "\n<output truncated>"
        return ToolResult(
            content=content,
            is_error=process.returncode != 0,
            metadata={
                "exit_code": process.returncode,
                "timed_out": False,
                "truncated": truncated,
            },
        )

