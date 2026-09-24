"""Capture task-scoped workspace changes without modifying the Git index.

The tracker compares file snapshots rather than running `git diff` so untracked
files can be represented too.  It never stages, commits, or otherwise mutates
the repository; the result is a read-only artifact for the timeline.
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
    """Compare Git-visible files before and after a run, including untracked files.

    Large and binary files retain only their digest and metadata.  That keeps
    the Web Console responsive and avoids putting arbitrary binary data into a
    JSON patch while still reporting that a file changed.
    """

    def __init__(self, workspace: Path, *, max_file_bytes: int = 1_000_000) -> None:
        self.workspace = workspace.expanduser().resolve()
        self.max_file_bytes = max_file_bytes
        self._before = self._capture()

    def collect(self, *, reset: bool = False) -> WorkspaceChanges:
        """Capture a second snapshot and compare it with the previous baseline."""
        after = self._capture()
        changes = self._compare(self._before, after)
        if reset:
            self._before = after
        return changes

    def _capture(self) -> _Snapshot:
        """Read Git's tracked/untracked file list and snapshot safe file content."""
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
        """Hash one path and retain text only when it is small enough to diff."""
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
        """Build structured changes and aggregate line counts from two snapshots."""
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
        """Create one file record, using a unified diff for retained text."""
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
