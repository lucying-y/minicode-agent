import asyncio
import os
import sys
from pathlib import Path

import pytest

from minicode_agent.execution import (
    PosixShellBackend,
    PowerShellBackend,
    ShellInfo,
    ShellUnavailableError,
    default_shell,
    detect_shell,
    platform_system_prompt,
)
from minicode_agent.security.workspace import (
    WorkspaceViolation,
    _validate_windows_input,
    _validate_windows_relative_path,
)


def test_powershell_invocation_is_explicit_utf8_and_noninteractive() -> None:
    backend = PowerShellBackend(
        ShellInfo(
            platform="windows",
            operating_system="Windows 11",
            kind="powershell",
            executable=r"C:\Program Files\PowerShell\7\pwsh.exe",
            name="PowerShell",
            version="7.5.2",
        )
    )

    invocation = backend.invocation("Get-Location")

    assert invocation[0].endswith("pwsh.exe")
    assert "-NoProfile" in invocation
    assert "-NonInteractive" in invocation
    assert "cmd.exe" not in " ".join(invocation).casefold()
    assert "UTF8Encoding" in invocation[-1]
    assert "Get-Location" in invocation[-1]
    assert backend.demo_command == "Get-Location"
    assert "PowerShell syntax" in backend.tool_description


async def test_windows_backend_forces_python_utf8_environment(monkeypatch, tmp_path: Path) -> None:
    backend = PowerShellBackend(
        ShellInfo(
            platform="windows",
            operating_system="Windows 11",
            kind="powershell",
            executable="pwsh.exe",
            name="PowerShell",
        )
    )
    captured: dict[str, object] = {}

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "legacy"

    await backend._start("Get-Location", tmp_path, environment)

    child_environment = captured["kwargs"]["env"]
    assert child_environment["PYTHONIOENCODING"] == "utf-8"
    assert child_environment["PYTHONUTF8"] == "1"
    assert environment["PYTHONIOENCODING"] == "legacy"


def test_posix_invocation_uses_explicit_shell() -> None:
    backend = PosixShellBackend(
        ShellInfo(
            platform="posix",
            operating_system="Linux",
            kind="posix",
            executable="/bin/sh",
            name="POSIX sh",
        )
    )

    assert backend.invocation("pwd") == ("/bin/sh", "-c", "pwd")
    assert backend.demo_command == "pwd"


def test_detect_shell_prefers_powershell_7(monkeypatch) -> None:
    def fake_which(command: str) -> str | None:
        if command == "pwsh.exe":
            return r"C:\Program Files\PowerShell\7\pwsh.exe"
        return None

    monkeypatch.setattr("minicode_agent.execution.shell.shutil.which", fake_which)
    monkeypatch.setattr(
        "minicode_agent.execution.shell._probe_powershell_version",
        lambda executable: "7.5.2",
    )

    backend = detect_shell(platform_name="win32", operating_system="Windows 11")

    assert isinstance(backend, PowerShellBackend)
    assert backend.info.name == "PowerShell"
    assert backend.info.version == "7.5.2"


def test_detect_shell_reports_missing_powershell(monkeypatch) -> None:
    monkeypatch.setattr("minicode_agent.execution.shell.shutil.which", lambda command: None)

    with pytest.raises(ShellUnavailableError, match="PowerShell is required"):
        detect_shell(platform_name="win32", operating_system="Windows 11")


def test_detect_shell_falls_back_to_windows_powershell(monkeypatch) -> None:
    def fake_which(command: str) -> str | None:
        if command == "powershell.exe":
            return r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
        return None

    monkeypatch.setattr("minicode_agent.execution.shell.shutil.which", fake_which)
    monkeypatch.setattr(
        "minicode_agent.execution.shell._probe_powershell_version",
        lambda executable: "5.1.22621.4391",
    )

    backend = detect_shell(platform_name="win32", operating_system="Windows 11")

    assert backend.info.name == "Windows PowerShell"
    assert backend.info.version == "5.1.22621.4391"


def test_platform_prompt_tells_model_to_use_powershell(tmp_path: Path) -> None:
    backend = PowerShellBackend(
        ShellInfo(
            platform="windows",
            operating_system="Windows 11",
            kind="powershell",
            executable="pwsh.exe",
            name="PowerShell",
            version="7.5.2",
        )
    )

    prompt = platform_system_prompt("Base prompt.", backend, tmp_path)

    assert "native PowerShell" in prompt
    assert "not Bash or CMD" in prompt
    assert str(tmp_path) in prompt
    assert "use `python`, not `python3`" in prompt


def test_windows_path_validation_blocks_drive_relative_ads_and_devices() -> None:
    with pytest.raises(WorkspaceViolation, match="drive-relative"):
        _validate_windows_input(r"C:relative\file.py")
    with pytest.raises(WorkspaceViolation, match="alternate data streams"):
        _validate_windows_relative_path(Path("file.txt:secret"))
    with pytest.raises(WorkspaceViolation, match="reserved path name"):
        _validate_windows_relative_path(Path("NUL.txt"))


async def test_detected_shell_handles_utf8_and_workspace_with_spaces(tmp_path: Path) -> None:
    workspace = tmp_path / "中文 workspace"
    workspace.mkdir()
    result = await default_shell().run(
        'python -c "print(\'你好\', end=\'\')"',
        cwd=workspace,
        timeout_seconds=10,
        max_chars=1_000,
    )

    assert result.exit_code == 0
    assert result.output == "你好"


async def test_cancelling_shell_command_terminates_process_tree(tmp_path: Path) -> None:
    execution = asyncio.create_task(
        default_shell().run(
            'python -c "import time; print(\'started\', flush=True); time.sleep(30)"',
            cwd=tmp_path,
            timeout_seconds=60,
            max_chars=1_000,
        )
    )
    await asyncio.sleep(0.2)

    execution.cancel()

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(execution, timeout=5)


@pytest.mark.skipif(sys.platform != "win32", reason="requires native Windows PowerShell")
async def test_native_windows_powershell_reports_failure_and_timeout(tmp_path: Path) -> None:
    backend = default_shell()
    failed = await backend.run(
        "Write-Output '失败输出'; exit 7",
        cwd=tmp_path,
        timeout_seconds=10,
        max_chars=1_000,
    )
    timed_out = await backend.run(
        'python -c "import time; time.sleep(10)"',
        cwd=tmp_path,
        timeout_seconds=1,
        max_chars=1_000,
    )

    assert failed.exit_code == 7
    assert "失败输出" in failed.output
    assert timed_out.timed_out
    assert timed_out.exit_code is None
