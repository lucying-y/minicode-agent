"""Workspace-scoped file inspection and editing tools."""

import re
from pathlib import Path

from pydantic import BaseModel, Field

from minicode_agent.runtime.types import ToolResult
from minicode_agent.security import PermissionLevel, Workspace, is_sensitive_path
from minicode_agent.tools.base import Tool

_IGNORED_PARTS = {".git", ".minicode", ".venv", "__pycache__", "node_modules"}


def _is_ignored(path: Path) -> bool:
    return any(part in _IGNORED_PARTS for part in path.parts) or is_sensitive_path(path)


class ReadFileInput(BaseModel):
    path: str
    start_line: int = Field(default=1, ge=1)
    end_line: int | None = Field(default=None, ge=1)
    max_chars: int = Field(default=12_000, ge=1, le=50_000)


class ReadFileTool(Tool[ReadFileInput]):
    name = "read_file"
    description = "Read a UTF-8 text file inside the workspace with optional line bounds."
    permission = PermissionLevel.READ
    input_model = ReadFileInput

    async def run(self, data: ReadFileInput, workspace: Workspace) -> ToolResult:
        path = workspace.resolve(data.path, must_exist=True)
        if not path.is_file():
            raise ValueError(f"not a file: {data.path}")
        lines = path.read_text(encoding="utf-8").splitlines()
        end = data.end_line or len(lines)
        if end < data.start_line:
            raise ValueError("end_line must be greater than or equal to start_line")
        selected = lines[data.start_line - 1 : end]
        content = "\n".join(
            f"{line_number:6}\t{line}"
            for line_number, line in enumerate(selected, start=data.start_line)
        )
        truncated = len(content) > data.max_chars
        if truncated:
            content = content[: data.max_chars] + "\n<output truncated>"
        return ToolResult(
            content=content,
            metadata={"path": workspace.relative(path), "truncated": truncated},
        )


class ListFilesInput(BaseModel):
    path: str = "."
    pattern: str = "*"
    max_results: int = Field(default=200, ge=1, le=1000)


class ListFilesTool(Tool[ListFilesInput]):
    name = "list_files"
    description = "List files recursively inside a workspace directory using a glob pattern."
    permission = PermissionLevel.READ
    input_model = ListFilesInput

    async def run(self, data: ListFilesInput, workspace: Workspace) -> ToolResult:
        directory = workspace.resolve(data.path, must_exist=True)
        if not directory.is_dir():
            raise ValueError(f"not a directory: {data.path}")
        matches = []
        for path in directory.rglob(data.pattern):
            if path.is_file() and not _is_ignored(path.relative_to(workspace.root)):
                matches.append(workspace.relative(path))
                if len(matches) >= data.max_results:
                    break
        return ToolResult(
            content="\n".join(sorted(matches)),
            metadata={"count": len(matches), "limited": len(matches) >= data.max_results},
        )


class SearchTextInput(BaseModel):
    query: str = Field(min_length=1)
    path: str = "."
    file_pattern: str = "*"
    regex: bool = False
    max_results: int = Field(default=100, ge=1, le=500)


class SearchTextTool(Tool[SearchTextInput]):
    name = "search_text"
    description = "Search text files in the workspace and return matching file names and lines."
    permission = PermissionLevel.READ
    input_model = SearchTextInput

    async def run(self, data: SearchTextInput, workspace: Workspace) -> ToolResult:
        directory = workspace.resolve(data.path, must_exist=True)
        if not directory.is_dir():
            raise ValueError(f"not a directory: {data.path}")
        pattern = re.compile(data.query if data.regex else re.escape(data.query))
        matches: list[str] = []
        for path in directory.rglob(data.file_pattern):
            if not path.is_file() or _is_ignored(path.relative_to(workspace.root)):
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (UnicodeDecodeError, OSError):
                continue
            for line_number, line in enumerate(lines, start=1):
                if pattern.search(line):
                    matches.append(f"{workspace.relative(path)}:{line_number}:{line}")
                    if len(matches) >= data.max_results:
                        return ToolResult(
                            content="\n".join(matches),
                            metadata={"count": len(matches), "limited": True},
                        )
        return ToolResult(
            content="\n".join(matches),
            metadata={"count": len(matches), "limited": False},
        )


class EditFileInput(BaseModel):
    path: str
    old_text: str
    new_text: str


class EditFileTool(Tool[EditFileInput]):
    name = "edit_file"
    description = (
        "Replace one exact, unique text block in a workspace file. "
        "Use an empty old_text only when creating a new file."
    )
    permission = PermissionLevel.WRITE
    input_model = EditFileInput

    async def run(self, data: EditFileInput, workspace: Workspace) -> ToolResult:
        path = workspace.resolve(data.path)
        if not path.exists():
            if data.old_text:
                raise FileNotFoundError(data.path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(data.new_text, encoding="utf-8")
            return ToolResult(content=f"created {workspace.relative(path)}")

        if not path.is_file():
            raise ValueError(f"not a file: {data.path}")
        if not data.old_text:
            raise ValueError("old_text cannot be empty when editing an existing file")
        if data.old_text == data.new_text:
            raise ValueError("old_text and new_text must differ")

        content = path.read_text(encoding="utf-8")
        occurrences = content.count(data.old_text)
        if occurrences != 1:
            raise ValueError(f"old_text must match exactly once; found {occurrences} matches")
        path.write_text(content.replace(data.old_text, data.new_text), encoding="utf-8")
        return ToolResult(content=f"edited {workspace.relative(path)}")
