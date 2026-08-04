"""Platform-aware command execution used by tools and evaluations."""

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
