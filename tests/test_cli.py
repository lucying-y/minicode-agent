from pathlib import Path

from minicode_agent.cli import AlwaysApprover, ConsoleApprover, async_main, build_parser
from minicode_agent.runtime import ToolCall
from minicode_agent.security import PermissionLevel


def test_parser_accepts_run_configuration() -> None:
    args = build_parser().parse_args(
        ["run", "fix the tests", "--workspace", "/tmp/project", "--max-steps", "5"]
    )

    assert args.command == "run"
    assert args.task == "fix the tests"
    assert args.workspace == Path("/tmp/project")
    assert args.max_steps == 5

    resume_args = build_parser().parse_args(["resume", "run-123", "--max-steps", "20"])
    assert resume_args.command == "resume"
    assert resume_args.run_id == "run-123"
    assert resume_args.max_steps == 20


async def test_demo_runs_without_api_key(tmp_path: Path, capsys) -> None:
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")

    exit_code = await async_main(["demo", "--workspace", str(tmp_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Demo completed after reading README.md." in output
    assert (tmp_path / ".minicode" / "traces.jsonl").exists()
    assert (tmp_path / ".minicode" / "checkpoints.db").exists()


async def test_run_reports_missing_environment_configuration(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.chdir(tmp_path)
    for name in ("MINICODE_API_KEY", "MINICODE_BASE_URL", "MINICODE_MODEL"):
        monkeypatch.delenv(name, raising=False)

    exit_code = await async_main(["run", "inspect", "--workspace", str(tmp_path)])

    assert exit_code == 2
    assert "Copy .env.example to .env" in capsys.readouterr().out


async def test_console_and_always_approvers(monkeypatch) -> None:
    call = ToolCall(id="1", name="edit_file", arguments={"path": "app.py"})
    monkeypatch.setattr("builtins.input", lambda prompt: "yes")

    assert await ConsoleApprover().approve(call, PermissionLevel.WRITE)
    assert await AlwaysApprover().approve(call, PermissionLevel.EXECUTE)


async def test_resume_reports_missing_checkpoint(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("MINICODE_API_KEY", "test-key")
    monkeypatch.setenv("MINICODE_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("MINICODE_MODEL", "test-model")

    exit_code = await async_main(["resume", "missing-run", "--workspace", str(tmp_path)])

    assert exit_code == 2
    assert "checkpoint not found: missing-run" in capsys.readouterr().out
