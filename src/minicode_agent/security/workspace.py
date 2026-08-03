"""Resolve tool paths inside one repository boundary."""

import os
from pathlib import Path


class WorkspaceViolation(ValueError):
    """Raised when a path escapes the configured workspace."""


class Workspace:
    """Canonical root used by all repository tools."""

    def __init__(self, root: Path) -> None:
        resolved = root.expanduser().resolve()
        if not resolved.is_dir():
            raise ValueError(f"workspace is not a directory: {resolved}")
        self.root = resolved

    def resolve(self, path: str, *, must_exist: bool = False) -> Path:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = self.root / candidate
        candidate = candidate.resolve(strict=False)

        if os.path.commonpath((self.root, candidate)) != str(self.root):
            raise WorkspaceViolation(f"path escapes workspace: {path}")
        if must_exist and not candidate.exists():
            raise FileNotFoundError(path)
        return candidate

    def relative(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

