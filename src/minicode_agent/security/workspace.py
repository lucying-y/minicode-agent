"""Resolve tool paths inside one repository boundary."""

import os
from pathlib import Path, PureWindowsPath

_SENSITIVE_DIRECTORIES = {".git", ".ssh"}
_SENSITIVE_FILES = {".netrc", ".npmrc", ".pypirc", "id_dsa", "id_ed25519", "id_rsa"}
_SAFE_ENV_TEMPLATES = {".env.example", ".env.sample", ".env.template"}


def is_sensitive_path(path: Path) -> bool:
    """Return whether a workspace-relative path commonly contains credentials."""
    for part in path.parts:
        normalized = part.casefold()
        if normalized in _SENSITIVE_DIRECTORIES or normalized in _SENSITIVE_FILES:
            return True
        if normalized.startswith(".env") and normalized not in _SAFE_ENV_TEMPLATES:
            return True
    return False


_WINDOWS_RESERVED_NAMES = {
    "aux",
    "clock$",
    "con",
    "nul",
    "prn",
    *(f"com{index}" for index in range(1, 10)),
    *(f"lpt{index}" for index in range(1, 10)),
}


def _validate_windows_input(path: str) -> None:
    parsed = PureWindowsPath(path)
    if parsed.drive and not parsed.root:
        raise WorkspaceViolation(f"drive-relative paths are blocked: {path}")


def _validate_windows_relative_path(path: Path) -> None:
    for part in path.parts:
        if ":" in part:
            raise WorkspaceViolation(f"Windows alternate data streams are blocked: {path}")
        normalized = part.rstrip(" .").split(".", 1)[0].casefold()
        if normalized in _WINDOWS_RESERVED_NAMES:
            raise WorkspaceViolation(f"Windows reserved path name is blocked: {path}")


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
        if os.name == "nt":
            _validate_windows_input(path)
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = self.root / candidate
        candidate = candidate.resolve(strict=False)

        try:
            relative = candidate.relative_to(self.root)
        except ValueError as exc:
            raise WorkspaceViolation(f"path escapes workspace: {path}") from exc
        if os.name == "nt":
            _validate_windows_relative_path(relative)
        if is_sensitive_path(relative):
            raise WorkspaceViolation(f"sensitive path is blocked: {path}")
        if must_exist and not candidate.exists():
            raise FileNotFoundError(path)
        return candidate

    def relative(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()
