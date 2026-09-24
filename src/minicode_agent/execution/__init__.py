"""供工具和评测使用的跨平台命令执行能力。

调用方使用统一的后端契约，无需自行根据 Windows 或 POSIX 的细节编写分支。
"""

from minicode_agent.execution.shell import (
    CommandResult,
    PosixShellBackend,
    PowerShellBackend,
    ShellBackend,
    ShellInfo,
    ShellUnavailableError,
    default_shell,
    detect_shell,
    platform_system_prompt,
)

__all__ = [
    "CommandResult",
    "PosixShellBackend",
    "PowerShellBackend",
    "ShellBackend",
    "ShellInfo",
    "ShellUnavailableError",
    "default_shell",
    "detect_shell",
    "platform_system_prompt",
]
