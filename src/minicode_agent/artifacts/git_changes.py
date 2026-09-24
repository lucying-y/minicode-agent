"""捕获任务范围内的工作区变更，并且不修改 Git 暂存区。

跟踪器通过比较文件快照而不是执行 `git diff`，因此也能表示未跟踪文件。它不会暂存、
提交或以其他方式修改仓库，生成的结果仅作为时间线中的只读产物。
"""

import difflib
import hashlib
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class FileChange(BaseModel):
    """One file that changed between two workspace snapshots."""

    path: str
    status: Literal["added", "modified", "deleted"]
    additions: int | None
    deletions: int | None
    binary: bool
    patch: str


class WorkspaceChanges(BaseModel):
    """Structured changes attributable to one task execution segment."""

    available: bool
    reason: str | None = None
    files: list[FileChange] = Field(default_factory=list)
    additions: int = 0
    deletions: int = 0


@dataclass(frozen=True)
class _FileState:
    exists: bool
    digest: str | None
    content: bytes | None
    binary: bool


@dataclass(frozen=True)
class _Snapshot:
    available: bool
    reason: str | None
    files: dict[str, _FileState]


class WorkspaceChangeTracker:
    """比较任务前后的 Git 可见文件，包括未跟踪文件。

    大文件和二进制文件只保留摘要及元数据。这样既能报告文件发生过变化，又能避免把任意
    二进制内容写入 JSON 补丁，并保持 Web Console 的响应速度。
    """

    def __init__(self, workspace: Path, *, max_file_bytes: int = 1_000_000) -> None:
        self.workspace = workspace.expanduser().resolve()
        self.max_file_bytes = max_file_bytes
        self._before = self._capture()

    def collect(self, *, reset: bool = False) -> WorkspaceChanges:
        """捕获新快照并与上一次基线比较。"""
        after = self._capture()
        changes = self._compare(self._before, after)
        if reset:
            self._before = after
        return changes

    def _capture(self) -> _Snapshot:
        """读取 Git 已跟踪和未跟踪文件列表，并为可安全读取的内容生成快照。"""
        try:
            result = subprocess.run(
                ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                cwd=self.workspace,
                check=False,
                capture_output=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return _Snapshot(False, f"Git snapshot unavailable: {exc}", {})
        if result.returncode != 0:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
            return _Snapshot(False, detail or "workspace is not a Git repository", {})

        files: dict[str, _FileState] = {}
        for raw_path in result.stdout.split(b"\0"):
            if not raw_path:
                continue
            relative = os.fsdecode(raw_path)
            normalized = relative.replace(os.sep, "/")
            if normalized == ".minicode" or normalized.startswith(".minicode/"):
                continue
            path = self.workspace / relative
            files[normalized] = self._read_state(path)
        return _Snapshot(True, None, files)

    def _read_state(self, path: Path) -> _FileState:
        """计算单个路径的摘要，仅在文本足够小时保留内容用于差异比较。"""
        if not path.exists() and not path.is_symlink():
            return _FileState(False, None, b"", False)
        try:
            content = os.readlink(path).encode("utf-8") if path.is_symlink() else path.read_bytes()
        except OSError:
            return _FileState(True, None, None, True)
        digest = hashlib.sha256(content).hexdigest()
        binary = b"\0" in content[:8_192]
        retained = content if len(content) <= self.max_file_bytes else None
        return _FileState(True, digest, retained, binary or retained is None)

    @staticmethod
    def _compare(before: _Snapshot, after: _Snapshot) -> WorkspaceChanges:
        """根据两个快照生成结构化变更并汇总增删行数。"""
        if not before.available:
            return WorkspaceChanges(available=False, reason=before.reason)
        if not after.available:
            return WorkspaceChanges(available=False, reason=after.reason)

        changes: list[FileChange] = []
        for path in sorted(before.files.keys() | after.files.keys()):
            old = before.files.get(path, _FileState(False, None, b"", False))
            new = after.files.get(path, _FileState(False, None, b"", False))
            if old.exists == new.exists and old.digest == new.digest:
                continue
            status: Literal["added", "modified", "deleted"]
            if not old.exists:
                status = "added"
            elif not new.exists:
                status = "deleted"
            else:
                status = "modified"
            changes.append(WorkspaceChangeTracker._file_change(path, status, old, new))

        additions = sum(item.additions or 0 for item in changes)
        deletions = sum(item.deletions or 0 for item in changes)
        return WorkspaceChanges(
            available=True,
            files=changes,
            additions=additions,
            deletions=deletions,
        )

    @staticmethod
    def _file_change(
        path: str,
        status: Literal["added", "modified", "deleted"],
        old: _FileState,
        new: _FileState,
    ) -> FileChange:
        """创建单个文件的变更记录，为保留的文本生成 unified diff。"""
        binary = old.binary or new.binary or old.content is None or new.content is None
        if binary:
            return FileChange(
                path=path,
                status=status,
                additions=None,
                deletions=None,
                binary=True,
                patch="",
            )

        old_text = old.content.decode("utf-8", errors="replace") if old.exists else ""
        new_text = new.content.decode("utf-8", errors="replace") if new.exists else ""
        old_lines = old_text.splitlines(keepends=True)
        new_lines = new_text.splitlines(keepends=True)
        additions = 0
        deletions = 0
        for tag, old_start, old_end, new_start, new_end in difflib.SequenceMatcher(
            None, old_lines, new_lines
        ).get_opcodes():
            if tag in {"replace", "delete"}:
                deletions += old_end - old_start
            if tag in {"replace", "insert"}:
                additions += new_end - new_start
        patch = "".join(
            difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
                n=3,
            )
        )
        return FileChange(
            path=path,
            status=status,
            additions=additions,
            deletions=deletions,
            binary=False,
            patch=patch,
        )
