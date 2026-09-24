"""在单个仓库边界内解析工具路径。

所有内置文件工具都会通过 `Workspace` 解析用户或模型提供的路径。路径检查在展开和规范化
之后执行，以便一致处理相对路径、符号链接和平台特定的路径写法。
"""

import os
from pathlib import Path, PureWindowsPath

_SENSITIVE_DIRECTORIES = {".git", ".ssh"}
_SENSITIVE_FILES = {".netrc", ".npmrc", ".pypirc", "id_dsa", "id_ed25519", "id_rsa"}
_SAFE_ENV_TEMPLATES = {".env.example", ".env.sample", ".env.template"}


def is_sensitive_path(path: Path) -> bool:
    """判断相对工作区的路径是否通常包含凭据。

    检查有意基于名称而不是文件内容。它会阻止 `.ssh`、`.git` 和 `.env` 等常见凭据路径，
    同时允许常见的环境变量示例或模板文件。
    """
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
    """拒绝依赖 Shell 当前状态才能确定含义的 Windows 驱动器相对路径。"""
    parsed = PureWindowsPath(path)
    if parsed.drive and not parsed.root:
        raise WorkspaceViolation(f"drive-relative paths are blocked: {path}")


def _validate_windows_relative_path(path: Path) -> None:
    """拒绝 Windows 设备保留名和备用数据流语法。"""
    for part in path.parts:
        if ":" in part:
            raise WorkspaceViolation(f"Windows alternate data streams are blocked: {path}")
        normalized = part.rstrip(" .").split(".", 1)[0].casefold()
        if normalized in _WINDOWS_RESERVED_NAMES:
            raise WorkspaceViolation(f"Windows reserved path name is blocked: {path}")


class WorkspaceViolation(ValueError):
    """Raised when a path escapes the configured workspace."""


class Workspace:
    """所有仓库工具共用的规范化根目录。

    `Workspace` 保存一个已解析的目录，只暴露两项操作：安全解析外部路径，以及生成已知路径
    相对于该目录的表示。它是共享的边界对象，不是文件系统沙箱。
    """

    def __init__(self, root: Path) -> None:
        resolved = root.expanduser().resolve()
        if not resolved.is_dir():
            raise ValueError(f"workspace is not a directory: {resolved}")
        self.root = resolved

    def resolve(self, path: str, *, must_exist: bool = False) -> Path:
        """解析路径，并拒绝越界、敏感或不符合平台规则的路径形式。"""
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
        """返回相对于工作区根目录的稳定 POSIX 风格路径。"""
        return path.relative_to(self.root).as_posix()
