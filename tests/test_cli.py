import json
from pathlib import Path

from minicode_agent.cli import AlwaysApprover, ConsoleApprover, async_main, build_parser
from minicode_agent.models import FakeModelProvider
from minicode_agent.runtime import ModelResponse, ToolCall
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

    eval_args = build_parser().parse_args(["eval", "--tasks", "custom.json"])
    assert eval_args.command == "eval"
    assert eval_args.tasks == Path("custom.json")
    assert eval_args.max_steps == 12


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


async def test_eval_reports_missing_task_suite(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("MINICODE_API_KEY", "test-key")
    monkeypatch.setenv("MINICODE_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("MINICODE_MODEL", "test-model")

    exit_code = await async_main(
        [
            "eval",
            "--tasks",
            str(tmp_path / "missing.json"),
            "--output",
            str(tmp_path / "output"),
        ]
    )

    assert exit_code == 2
    assert "Unable to load evaluation tasks" in capsys.readouterr().out


async def test_eval_cli_runs_suite_and_writes_report(tmp_path: Path, monkeypatch, capsys) -> None:
    class ClosableFakeModel(FakeModelProvider):
        async def aclose(self) -> None:
            return None

    task_path = tmp_path / "tasks.json"
    task_path.write_text(
        json.dumps(
            {
                "version": 1,
                "tasks": [
                    {
                        "id": "fix-value",
                        "prompt": "Change value to 2",
                        "files": {"app.py": "value = 1\n"},
                        "verify_command": (
                            "python3 -c 'from app import value; assert value == 2'"
                        ),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    fake_model = ClosableFakeModel(
        [
            ModelResponse(
                tool_calls=[
                    ToolCall(
                        id="edit-1",
                        name="edit_file",
                        arguments={"path": "app.py", "old_text": "1", "new_text": "2"},
                    )
                ]
            ),
            ModelResponse(content="done"),
        ]
    )
    monkeypatch.setenv("MINICODE_API_KEY", "test-key")
    monkeypatch.setenv("MINICODE_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("MINICODE_MODEL", "fake-model")
    monkeypatch.setattr(
        "minicode_agent.cli.OpenAICompatibleProvider",
        lambda **kwargs: fake_model,
    )
    output_root = tmp_path / "reports"

    exit_code = await async_main(
        ["eval", "--tasks", str(task_path), "--output", str(output_root)]
    )

    assert exit_code == 0
    assert "passed=1/1" in capsys.readouterr().out
    reports = list(output_root.glob("*/report.json"))
    assert len(reports) == 1
    assert json.loads(reports[0].read_text(encoding="utf-8"))["success_rate"] == 1.0
