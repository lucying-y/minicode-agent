from pathlib import Path

from minicode_agent.artifacts import WorkspaceChangeTracker, extract_test_result


def _git(workspace: Path, *args: str) -> None:
    import subprocess

    subprocess.run(["git", *args], cwd=workspace, check=True, capture_output=True)


def test_workspace_change_tracker_reports_task_scoped_changes(tmp_path: Path) -> None:
    _git(tmp_path, "init")
    tracked = tmp_path / "app.py"
    tracked.write_text("value = 1\n", encoding="utf-8")
    _git(tmp_path, "add", "app.py")
    _git(
        tmp_path,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.com",
        "commit",
        "-m",
        "initial",
    )
    existing = tmp_path / "existing.txt"
    existing.write_text("already dirty\n", encoding="utf-8")
    tracker = WorkspaceChangeTracker(tmp_path)

    tracked.write_text("value = 2\n", encoding="utf-8")
    created = tmp_path / "new.py"
    created.write_text("print('new')\n", encoding="utf-8")
    internal = tmp_path / ".minicode"
    internal.mkdir()
    (internal / "runs.db").write_bytes(b"internal state")
    changes = tracker.collect()

    assert [change.path for change in changes.files] == ["app.py", "new.py"]
    assert [change.status for change in changes.files] == ["modified", "added"]
    assert changes.additions == 2
    assert changes.deletions == 1
    assert "-value = 1" in changes.files[0].patch
    assert "+value = 2" in changes.files[0].patch


def test_workspace_change_tracker_reports_non_git_workspace(tmp_path: Path) -> None:
    changes = WorkspaceChangeTracker(tmp_path).collect()

    assert not changes.available
    assert changes.reason


def test_extract_test_result_from_pytest_tool_event() -> None:
    result = extract_test_result(
        {
            "call": {
                "name": "run_shell",
                "arguments": {"command": "uv run pytest -q"},
            },
            "result": {
                "content": "66 passed, 1 skipped in 2.75s",
                "metadata": {
                    "exit_code": 0,
                    "timed_out": False,
                    "duration_ms": 2750.5,
                },
            },
        }
    )

    assert result is not None
    assert result.status == "passed"
    assert result.passed == 66
    assert result.skipped == 1
    assert result.duration_ms == 2750.5


def test_extract_test_result_ignores_non_test_commands() -> None:
    assert (
        extract_test_result(
            {
                "call": {"name": "run_shell", "arguments": {"command": "git status"}},
                "result": {"content": "", "metadata": {"exit_code": 0}},
            }
        )
        is None
    )


def test_extract_test_result_preserves_zero_failures() -> None:
    result = extract_test_result(
        {
            "call": {"name": "run_shell", "arguments": {"command": "npm test"}},
            "result": {
                "content": "12 passed, 0 failed",
                "metadata": {"exit_code": 0, "duration_ms": 10},
            },
        }
    )

    assert result is not None
    assert result.failed == 0
