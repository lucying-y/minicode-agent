from pathlib import Path

from minicode_agent.cli import async_main, build_parser


def test_parser_accepts_run_configuration() -> None:
    args = build_parser().parse_args(
        ["run", "fix the tests", "--workspace", "/tmp/project", "--max-steps", "5"]
    )

    assert args.command == "run"
    assert args.task == "fix the tests"
    assert args.workspace == Path("/tmp/project")
    assert args.max_steps == 5


async def test_demo_runs_without_api_key(tmp_path: Path, capsys) -> None:
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")

    exit_code = await async_main(["demo", "--workspace", str(tmp_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Demo completed after reading README.md." in output
    assert (tmp_path / ".minicode" / "traces.jsonl").exists()

