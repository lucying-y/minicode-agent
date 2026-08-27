import asyncio
import json
from pathlib import Path

import pytest

from minicode_agent.cli import (
    ConsoleApprover,
    _default_web_dist,
    _normalize_chat_input,
    async_main,
    build_parser,
)
from minicode_agent.models import FakeModelProvider
from minicode_agent.persistence import SqliteCheckpointStore, SqliteRunStore
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
    assert args.max_total_tokens == 100_000
    assert args.approval_mode == "ask"
    assert args.preset == "standard"

    auto_args = build_parser().parse_args(["run", "fix", "--approval-mode", "auto"])
    assert auto_args.approval_mode == "auto"
    assert not auto_args.yes

    yes_args = build_parser().parse_args(["run", "fix", "--yes"])
    assert yes_args.yes

    chat_args = build_parser().parse_args(["chat", "--workspace", "/tmp/chat"])
    assert chat_args.command == "chat"
    assert chat_args.workspace == Path("/tmp/chat")
    assert chat_args.preset == "standard"
    assert build_parser().parse_args([]).command is None

    minimal_args = build_parser().parse_args(["chat", "--preset", "minimal"])
    assert minimal_args.preset == "minimal"

    resume_args = build_parser().parse_args(["resume", "run-123", "--max-steps", "20"])
    assert resume_args.command == "resume"
    assert resume_args.run_id == "run-123"
    assert resume_args.max_steps == 20

    eval_args = build_parser().parse_args(["eval", "--tasks", "custom.json"])
    assert eval_args.command == "eval"
    assert eval_args.tasks == Path("custom.json")
    assert eval_args.max_steps == 12

    web_args = build_parser().parse_args(["web", "--port", "9000", "--demo"])
    assert web_args.command == "web"
    assert web_args.port == 9000
    assert web_args.web_dist == _default_web_dist()
    assert web_args.workspace == Path.cwd()
    assert web_args.demo


def test_chat_input_repairs_surrogate_escaped_command_prefix() -> None:
    assert _normalize_chat_input("\udce3/help") == "/help"
    assert _normalize_chat_input("\x1b[200~/status\x1b[201~") == "/status"


async def test_web_rejects_invalid_default_workspace(tmp_path: Path, capsys) -> None:
    exit_code = await async_main(
        ["web", "--demo", "--workspace", str(tmp_path / "missing")]
    )

    assert exit_code == 2
    assert "Invalid default workspace" in capsys.readouterr().out


async def test_demo_runs_without_api_key(tmp_path: Path, capsys) -> None:
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")

    exit_code = await async_main(["demo", "--workspace", str(tmp_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Demo completed after reading README.md." in output
    assert (tmp_path / ".minicode" / "traces.jsonl").exists()
    assert (tmp_path / ".minicode" / "checkpoints.db").exists()
    assert (tmp_path / ".minicode" / "runs.db").exists()
    runs = SqliteRunStore(tmp_path).list_runs()
    assert len(runs) == 1
    assert runs[0].source == "cli"
    assert runs[0].status == "completed"
    assert runs[0].output == "Demo completed after reading README.md."


async def test_run_reports_missing_environment_configuration(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.chdir(tmp_path)
    for name in ("MINICODE_API_KEY", "MINICODE_BASE_URL", "MINICODE_MODEL"):
        monkeypatch.delenv(name, raising=False)

    exit_code = await async_main(["run", "inspect", "--workspace", str(tmp_path)])

    assert exit_code == 2
    assert "Copy .env.example to .env" in capsys.readouterr().out


async def test_chat_keeps_context_and_clear_starts_new_run(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    fake_model = FakeModelProvider(
        [
            ModelResponse(content="first answer"),
            ModelResponse(content="second answer"),
        ],
        streaming=True,
        stream_chunk_size=4,
    )
    answers = iter(
        [
            "first question",
            "follow up",
            "/status",
            "/history",
            "/clear",
            "/exit",
        ]
    )
    monkeypatch.setenv("MINICODE_API_KEY", "test-key")
    monkeypatch.setenv("MINICODE_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("MINICODE_MODEL", "fake-model")
    monkeypatch.setattr(
        "minicode_agent.cli.OpenAICompatibleProvider",
        lambda **kwargs: fake_model,
    )
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))

    exit_code = await async_main(
        ["chat", "--workspace", str(tmp_path), "--preset", "minimal"]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "MiniCode Agent" in output
    assert "Preset: minimal" in output
    assert "first answer" in output
    assert "second answer" in output
    assert "1. first question" in output
    assert "2. follow up" in output
    assert "Context cleared. New Run ID:" in output
    first_request, _ = fake_model.requests[0]
    assert "Runtime environment:" in first_request[0].content
    _, first_tools = fake_model.requests[0]
    assert {tool.name for tool in first_tools} == {"read_file", "list_files", "search_text"}
    second_request, _ = fake_model.requests[1]
    assert [(message.role, message.content) for message in second_request[-3:]] == [
        ("user", "first question"),
        ("assistant", "first answer"),
        ("user", "follow up"),
    ]
    runs = SqliteRunStore(tmp_path).list_runs()
    assert len(runs) == 2
    first_run = next(run for run in runs if run.task == "first question")
    assert first_run.mode == "chat"
    assert first_run.status == "completed"
    event_types = [
        event["event_type"]
        for event in SqliteRunStore(tmp_path).list_events(first_run.run_id)
    ]
    assert event_types.count("user_message") == 2
    assert "session_waiting_input" in event_types
    assert event_types[-1] == "session_finished"


async def test_bare_cli_command_enters_chat_in_current_directory(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MINICODE_API_KEY", "test-key")
    monkeypatch.setenv("MINICODE_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("MINICODE_MODEL", "fake-model")
    monkeypatch.setattr(
        "minicode_agent.cli.OpenAICompatibleProvider",
        lambda **kwargs: FakeModelProvider([]),
    )
    monkeypatch.setattr("builtins.input", lambda prompt: "/exit")

    exit_code = await async_main([])

    assert exit_code == 0
    assert f"Workspace: {tmp_path}" in capsys.readouterr().out
    runs = SqliteRunStore(tmp_path).list_runs()
    assert len(runs) == 1
    assert runs[0].mode == "chat"
    assert runs[0].status == "completed"


async def test_help_command_with_surrogate_prefix_does_not_start_model(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    fake_model = FakeModelProvider([])
    answers = iter(["\udce3/help", "/exit"])
    monkeypatch.setenv("MINICODE_API_KEY", "test-key")
    monkeypatch.setenv("MINICODE_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("MINICODE_MODEL", "fake-model")
    monkeypatch.setattr(
        "minicode_agent.cli.OpenAICompatibleProvider",
        lambda **kwargs: fake_model,
    )
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))

    exit_code = await async_main(["chat", "--workspace", str(tmp_path)])

    assert exit_code == 0
    assert "Commands:" in capsys.readouterr().out
    assert fake_model.requests == []


async def test_console_approver(monkeypatch) -> None:
    call = ToolCall(id="1", name="edit_file", arguments={"path": "app.py"})
    monkeypatch.setattr("builtins.input", lambda prompt: "yes")

    assert await ConsoleApprover().approve(call, PermissionLevel.WRITE)


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
                            'python -c "from app import value; assert value == 2"'
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


async def test_cli_reports_missing_platform_shell(tmp_path: Path, monkeypatch, capsys) -> None:
    from minicode_agent.execution import ShellUnavailableError

    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")

    def missing_shell():
        raise ShellUnavailableError("PowerShell is required")

    monkeypatch.setattr("minicode_agent.cli.default_shell", missing_shell)

    exit_code = await async_main(["demo", "--workspace", str(tmp_path)])

    assert exit_code == 2
    assert "Shell unavailable: PowerShell is required" in capsys.readouterr().out


async def test_cli_interruption_persists_cancelled_run(tmp_path: Path, monkeypatch) -> None:
    class CancellingProvider(FakeModelProvider):
        async def complete(self, messages, tools):
            del messages, tools
            raise asyncio.CancelledError

        async def aclose(self) -> None:
            return None

    monkeypatch.setenv("MINICODE_API_KEY", "test-key")
    monkeypatch.setenv("MINICODE_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("MINICODE_MODEL", "cancel-model")
    monkeypatch.setattr(
        "minicode_agent.cli.OpenAICompatibleProvider",
        lambda **kwargs: CancellingProvider([]),
    )

    with pytest.raises(asyncio.CancelledError):
        await async_main(["run", "cancel me", "--workspace", str(tmp_path)])

    run = SqliteRunStore(tmp_path).list_runs()[0]
    checkpoint = SqliteCheckpointStore(
        tmp_path / ".minicode" / "checkpoints.db"
    ).load(run.run_id)
    assert run.status == "cancelled"
    assert checkpoint is not None
    assert checkpoint.status == "cancelled"
