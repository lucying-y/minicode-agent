from pathlib import Path

from minicode_agent.runtime import ToolCall
from minicode_agent.security import PermissionLevel, PermissionPolicy
from minicode_agent.tools import create_default_registry


class StaticApprover:
    def __init__(self, approved: bool) -> None:
        self.approved = approved
        self.requests: list[tuple[ToolCall, PermissionLevel]] = []

    async def approve(self, call: ToolCall, permission: PermissionLevel) -> bool:
        self.requests.append((call, permission))
        return self.approved


async def test_read_and_search_are_workspace_scoped(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text("value = 42\nprint(value)\n", encoding="utf-8")
    registry = create_default_registry(tmp_path)

    read_result = await registry.execute(
        ToolCall(id="1", name="read_file", arguments={"path": "app.py"})
    )
    search_result = await registry.execute(
        ToolCall(id="2", name="search_text", arguments={"query": "42", "path": "."})
    )
    escape_result = await registry.execute(
        ToolCall(id="3", name="read_file", arguments={"path": "../outside.txt"})
    )

    assert not read_result.is_error
    assert "1\tvalue = 42" in read_result.content
    assert "app.py:1:value = 42" in search_result.content
    assert escape_result.is_error
    assert "escapes workspace" in escape_result.content


async def test_sensitive_files_are_hidden_and_blocked(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("API_KEY=secret\n", encoding="utf-8")
    (tmp_path / ".env.example").write_text("API_KEY=replace-me\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("value = 42\n", encoding="utf-8")
    registry = create_default_registry(tmp_path)

    listed = await registry.execute(
        ToolCall(id="1", name="list_files", arguments={"pattern": "*"})
    )
    secret = await registry.execute(
        ToolCall(id="2", name="read_file", arguments={"path": ".env"})
    )
    template = await registry.execute(
        ToolCall(id="3", name="read_file", arguments={"path": ".env.example"})
    )

    assert ".env" not in listed.content.splitlines()
    assert ".env.example" in listed.content.splitlines()
    assert secret.is_error
    assert "sensitive path is blocked" in secret.content
    assert not template.is_error


async def test_edit_requires_approval_and_exact_match(tmp_path: Path) -> None:
    target = tmp_path / "app.py"
    target.write_text("answer = 41\n", encoding="utf-8")
    denied_registry = create_default_registry(tmp_path)

    denied = await denied_registry.execute(
        ToolCall(
            id="1",
            name="edit_file",
            arguments={"path": "app.py", "old_text": "41", "new_text": "42"},
        )
    )

    assert denied.is_error
    assert target.read_text(encoding="utf-8") == "answer = 41\n"

    approver = StaticApprover(True)
    allowed_registry = create_default_registry(tmp_path, PermissionPolicy(approver))
    allowed = await allowed_registry.execute(
        ToolCall(
            id="2",
            name="edit_file",
            arguments={"path": "app.py", "old_text": "41", "new_text": "42"},
        )
    )

    assert not allowed.is_error
    assert target.read_text(encoding="utf-8") == "answer = 42\n"
    assert approver.requests[0][1] is PermissionLevel.WRITE


async def test_tool_metrics_separate_authorization_and_execution(
    tmp_path: Path,
    monkeypatch,
) -> None:
    (tmp_path / "app.py").write_text("value = 1\n", encoding="utf-8")
    registry = create_default_registry(tmp_path, PermissionPolicy(StaticApprover(True)))
    timestamps = iter([1.0, 3.0, 3.25])
    monkeypatch.setattr(
        "minicode_agent.tools.registry.perf_counter",
        lambda: next(timestamps),
    )

    result = await registry.execute(
        ToolCall(
            id="metrics",
            name="edit_file",
            arguments={"path": "app.py", "old_text": "1", "new_text": "2"},
        )
    )

    assert result.metadata["authorization_ms"] == 2000.0
    assert result.metadata["duration_ms"] == 250.0


async def test_shell_requires_approval_and_blocks_high_risk_commands(tmp_path: Path) -> None:
    approver = StaticApprover(True)
    registry = create_default_registry(tmp_path, PermissionPolicy(approver))

    safe = await registry.execute(
        ToolCall(id="1", name="run_shell", arguments={"command": "printf 'ok'"})
    )
    dangerous = await registry.execute(
        ToolCall(id="2", name="run_shell", arguments={"command": "rm -rf build"})
    )

    assert not safe.is_error
    assert safe.content == "ok"
    assert safe.metadata["exit_code"] == 0
    assert dangerous.is_error
    assert "blocked high-risk pattern" in dangerous.content


async def test_registry_returns_structured_errors(tmp_path: Path) -> None:
    registry = create_default_registry(tmp_path)

    unknown = await registry.execute(ToolCall(id="1", name="missing", arguments={}))
    invalid = await registry.execute(
        ToolCall(id="2", name="read_file", arguments={"start_line": 0})
    )

    assert unknown.is_error
    assert unknown.content == "unknown tool: missing"
    assert invalid.is_error
    assert invalid.metadata["tool"] == "read_file"


async def test_list_ignores_dependency_directories_and_edit_can_create(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('app')\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "ignored.py").write_text("ignored\n", encoding="utf-8")
    approver = StaticApprover(True)
    registry = create_default_registry(tmp_path, PermissionPolicy(approver))

    listed = await registry.execute(
        ToolCall(id="1", name="list_files", arguments={"pattern": "*.py"})
    )
    created = await registry.execute(
        ToolCall(
            id="2",
            name="edit_file",
            arguments={"path": "src/new.py", "old_text": "", "new_text": "value = 1\n"},
        )
    )

    assert listed.content == "src/app.py"
    assert not created.is_error
    assert (tmp_path / "src" / "new.py").read_text(encoding="utf-8") == "value = 1\n"


async def test_shell_reports_failure_and_timeout(tmp_path: Path) -> None:
    registry = create_default_registry(tmp_path, PermissionPolicy(StaticApprover(True)))

    failed = await registry.execute(
        ToolCall(id="1", name="run_shell", arguments={"command": "printf 'bad'; exit 3"})
    )
    timed_out = await registry.execute(
        ToolCall(
            id="2",
            name="run_shell",
            arguments={
                "command": "python3 -c 'import time; time.sleep(2)'",
                "timeout_seconds": 1,
            },
        )
    )

    assert failed.is_error
    assert failed.content == "bad"
    assert failed.metadata["exit_code"] == 3
    assert timed_out.is_error
    assert timed_out.metadata["timed_out"] is True
