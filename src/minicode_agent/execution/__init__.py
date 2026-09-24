"""Platform-aware command execution used by tools and evaluations.

Callers use the shared backend contract rather than branching on Windows or
POSIX details themselves.
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
