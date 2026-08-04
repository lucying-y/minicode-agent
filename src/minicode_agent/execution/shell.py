"""Execute commands with explicit POSIX or PowerShell semantics."""

import asyncio
import os
import platform
import shutil
import signal
import subprocess
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal


class ShellUnavailableError(OSError):
    """Raised when the host has no supported command interpreter."""


@dataclass(frozen=True)
class ShellInfo:
    """Stable shell details exposed to the model, CLI, and Web Console."""

    platform: Literal["windows", "posix"]
    operating_system: str
    kind: Literal["powershell", "posix"]
    executable: str
    name: str
    version: str | None = None

    @property
    def display_name(self) -> str:
        return f"{self.name} {self.version}" if self.version else self.name


@dataclass(frozen=True)
class CommandResult:
    """Bounded output and process status from one shell command."""

    output: str
    exit_code: int | None
    timed_out: bool
    truncated: bool


class ShellBackend(ABC):
    """Run commands in one explicit shell without an implicit parent shell."""

    def __init__(self, info: ShellInfo) -> None:
        self.info = info

    @property
    @abstractmethod
    def demo_command(self) -> str:
        """Return a harmless command that prints the current directory."""

    @property
    @abstractmethod
    def tool_description(self) -> str:
        """Describe command semantics to the model."""

    @abstractmethod
    def invocation(self, command: str) -> tuple[str, ...]:
        """Build the executable and arguments for one command."""

    async def run(
        self,
        command: str,
        *,
        cwd: Path,
        timeout_seconds: int,
        max_chars: int,
        environment: dict[str, str] | None = None,
    ) -> CommandResult:
        process = await self._start(command, cwd, environment)
        try:
            output, _ = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout_seconds,
            )
        except asyncio.CancelledError:
            await self._terminate_tree(process)
            raise
        except TimeoutError:
            await self._terminate_tree(process)
            return CommandResult(
                output=f"command timed out after {timeout_seconds}s",
                exit_code=None,
                timed_out=True,
                truncated=False,
            )

        content = output.decode("utf-8", errors="replace")
        truncated = len(content) > max_chars
        if truncated:
            content = content[:max_chars] + "\n<output truncated>"
        return CommandResult(
            output=content,
            exit_code=process.returncode,
            timed_out=False,
            truncated=truncated,
        )

    async def _start(
        self,
        command: str,
        cwd: Path,
        environment: dict[str, str] | None,
    ) -> asyncio.subprocess.Process:
        invocation = self.invocation(command)
        options: dict[str, object] = {
            "cwd": cwd,
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.STDOUT,
        }
        if environment is not None:
            options["env"] = environment
        if self.info.platform == "windows":
            options["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            options["start_new_session"] = True
        return await asyncio.create_subprocess_exec(*invocation, **options)

    async def _terminate_tree(self, process: asyncio.subprocess.Process) -> None:
        if self.info.platform == "windows":
            await _terminate_windows_process_tree(process)
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                if process.returncode is None:
                    try:
                        process.kill()
                    except ProcessLookupError:
                        pass
        await process.communicate()


class PosixShellBackend(ShellBackend):
    """Execute commands with an explicit POSIX-compatible shell."""

    @property
    def demo_command(self) -> str:
        return "pwd"

    @property
    def tool_description(self) -> str:
        return "Run one POSIX shell command in the workspace with a timeout and bounded output."

    def invocation(self, command: str) -> tuple[str, ...]:
        return (self.info.executable, "-c", command)


class PowerShellBackend(ShellBackend):
    """Execute commands with native PowerShell and deterministic UTF-8 output."""

    @property
    def demo_command(self) -> str:
        return "Get-Location"

    @property
    def tool_description(self) -> str:
        return (
            "Run one native PowerShell command in the workspace with a timeout and bounded output. "
            "Use PowerShell syntax, not Bash or CMD syntax."
        )

    def invocation(self, command: str) -> tuple[str, ...]:
        script = (
            "$ErrorActionPreference = 'Continue'\n"
            "[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)\n"
            "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)\n"
            "$OutputEncoding = [Console]::OutputEncoding\n"
            "& {\n"
            f"{command}\n"
            "}\n"
            "$minicodeSucceeded = $?\n"
            "$minicodeNativeExitCode = $LASTEXITCODE\n"
            "if ($null -ne $minicodeNativeExitCode -and $minicodeNativeExitCode -ne 0) { "
            "exit $minicodeNativeExitCode }\n"
            "if (-not $minicodeSucceeded) { exit 1 }\n"
            "exit 0"
        )
        return (
            self.info.executable,
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            script,
        )


async def _terminate_windows_process_tree(process: asyncio.subprocess.Process) -> None:
    taskkill = shutil.which("taskkill.exe") or shutil.which("taskkill")
    if taskkill is not None:
        terminator = await asyncio.create_subprocess_exec(
            taskkill,
            "/PID",
            str(process.pid),
            "/T",
            "/F",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await terminator.communicate()
    if process.returncode is None:
        try:
            process.kill()
        except ProcessLookupError:
            pass


def _probe_powershell_version(executable: str) -> str | None:
    try:
        result = subprocess.run(
            [
                executable,
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "$PSVersionTable.PSVersion.ToString()",
            ],
            check=False,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    version = result.stdout.strip()
    return version or None


def detect_shell(
    *,
    platform_name: str | None = None,
    operating_system: str | None = None,
) -> ShellBackend:
    """Detect PowerShell on Windows and an explicit POSIX shell elsewhere."""
    resolved_platform = platform_name or sys.platform
    resolved_os = operating_system or platform.system() or resolved_platform
    if resolved_platform == "win32":
        executable = shutil.which("pwsh.exe") or shutil.which("pwsh")
        name = "PowerShell"
        if executable is None:
            executable = shutil.which("powershell.exe") or shutil.which("powershell")
            name = "Windows PowerShell"
        if executable is None:
            raise ShellUnavailableError(
                "PowerShell is required on Windows; install PowerShell 7 or enable "
                "Windows PowerShell"
            )
        return PowerShellBackend(
            ShellInfo(
                platform="windows",
                operating_system=resolved_os,
                kind="powershell",
                executable=executable,
                name=name,
                version=_probe_powershell_version(executable),
            )
        )

    executable = shutil.which("sh")
    if executable is None:
        raise ShellUnavailableError("a POSIX-compatible sh executable is required")
    return PosixShellBackend(
        ShellInfo(
            platform="posix",
            operating_system=resolved_os,
            kind="posix",
            executable=executable,
            name="POSIX sh",
        )
    )


@lru_cache(maxsize=1)
def default_shell() -> ShellBackend:
    """Return the process-wide detected shell backend."""
    return detect_shell()


def platform_system_prompt(base_prompt: str, shell: ShellBackend, workspace: Path) -> str:
    """Tell the model which command language and path conventions are available."""
    if shell.info.platform == "windows":
        instructions = (
            f"Runtime environment: operating system={shell.info.operating_system}; "
            f"shell={shell.info.display_name}; workspace={workspace}. "
            "Shell tool calls run in native PowerShell. Use PowerShell syntax, not Bash or CMD "
            "syntax. Prefer the structured file tools for reading, searching, and editing. Use "
            "PowerShell mainly for Git, tests, package managers, and project commands. Quote paths "
            "that contain spaces and use `python`, not `python3`, when invoking the active Python "
            "environment."
        )
    else:
        instructions = (
            f"Runtime environment: operating system={shell.info.operating_system}; "
            f"shell={shell.info.display_name}; workspace={workspace}. "
            "Shell tool calls use POSIX shell syntax. Prefer the structured file tools for "
            "reading, searching, and editing."
        )
    return f"{base_prompt.rstrip()} {instructions}"
