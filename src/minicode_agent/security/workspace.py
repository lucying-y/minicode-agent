"""Resolve tool paths inside one repository boundary."""

import os
from pathlib import Path

_SENSITIVE_DIRECTORIES = {".git", ".ssh"}
_SENSITIVE_FILES = {".netrc", ".npmrc", ".pypirc", "id_dsa", "id_ed25519", "id_rsa"}
_SAFE_ENV_TEMPLATES = {".env.example", ".env.sample", ".env.template"}


def is_sensitive_path(path: Path) -> bool:
    """Return whether a workspace-relative path commonly contains credentials."""
    for part in path.parts:
        if part in _SENSITIVE_DIRECTORIES or part in _SENSITIVE_FILES:
            return True
        if part.startswith(".env") and part not in _SAFE_ENV_TEMPLATES:
            return True
    return False


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
        if is_sensitive_path(candidate.relative_to(self.root)):
            raise WorkspaceViolation(f"sensitive path is blocked: {path}")
        if must_exist and not candidate.exists():
            raise FileNotFoundError(path)
        return candidate

    def relative(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()
