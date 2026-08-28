"""Default repository tool set."""

from collections.abc import Iterable
from pathlib import Path

from minicode_agent.execution import ShellBackend
from minicode_agent.security import PermissionPolicy, Workspace
from minicode_agent.tools.filesystem import (
    EditFileTool,
    ListFilesTool,
    ReadFileTool,
    SearchTextTool,
)
from minicode_agent.tools.hooks import ToolHook
from minicode_agent.tools.registry import ToolRegistry
from minicode_agent.tools.shell import RunShellTool


def create_default_registry(
    root: Path,
    policy: PermissionPolicy | None = None,
    shell: ShellBackend | None = None,
    allowed_tools: set[str] | None = None,
    hooks: Iterable[ToolHook] = (),
) -> ToolRegistry:
    """Create workspace tools, optionally limited to a named capability set."""
    registry = ToolRegistry(Workspace(root), policy, hooks=hooks)
    default_tools = (
        ReadFileTool(),
        ListFilesTool(),
        SearchTextTool(),
        EditFileTool(),
        RunShellTool(shell),
    )
    known_tools = {tool.name for tool in default_tools}
    unknown_tools = (allowed_tools or set()) - known_tools
    if unknown_tools:
        names = ", ".join(sorted(unknown_tools))
        raise ValueError(f"unknown default tool names: {names}")
    for tool in default_tools:
        if allowed_tools is not None and tool.name not in allowed_tools:
            continue
        registry.register(tool)
    return registry
