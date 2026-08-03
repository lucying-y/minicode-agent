"""Default repository tool set."""

from pathlib import Path

from minicode_agent.security import PermissionPolicy, Workspace
from minicode_agent.tools.filesystem import (
    EditFileTool,
    ListFilesTool,
    ReadFileTool,
    SearchTextTool,
)
from minicode_agent.tools.registry import ToolRegistry
from minicode_agent.tools.shell import RunShellTool


def create_default_registry(
    root: Path,
    policy: PermissionPolicy | None = None,
) -> ToolRegistry:
    registry = ToolRegistry(Workspace(root), policy)
    for tool in (ReadFileTool(), ListFilesTool(), SearchTextTool(), EditFileTool(), RunShellTool()):
        registry.register(tool)
    return registry

