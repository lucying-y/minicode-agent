"""Command-line entry point for MiniCode Agent."""

import argparse
import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

from minicode_agent.evaluation import EvaluationRunner, load_task_suite
from minicode_agent.models import FakeModelProvider, OpenAICompatibleProvider
from minicode_agent.persistence import JsonlTraceSink, SqliteCheckpointStore
from minicode_agent.runtime import AgentConfig, AgentRuntime, ModelResponse, RunStatus, ToolCall
from minicode_agent.security import PermissionLevel, PermissionPolicy
from minicode_agent.tools import create_default_registry


class ConsoleApprover:
    """Ask before each write or shell operation."""

    async def approve(self, call: ToolCall, permission: PermissionLevel) -> bool:
        print(f"\nApproval required: {permission.value} via {call.name}")
        print(json.dumps(call.arguments, ensure_ascii=False, indent=2))
        try:
            answer = await asyncio.to_thread(input, "Allow this operation? [y/N] ")
        except EOFError:
            return False
        return answer.strip().lower() in {"y", "yes"}


class AlwaysApprover:
    """Approve non-blocked operations for explicit `--yes` runs."""

    async def approve(self, call: ToolCall, permission: PermissionLevel) -> bool:
        del call, permission
        return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="minicode", description="A small coding-agent runtime")
    subparsers = parser.add_subparsers(dest="command", required=True)

    demo = subparsers.add_parser("demo", help="run a deterministic demo without an API key")
    demo.add_argument("--workspace", type=Path, default=Path.cwd())

    run = subparsers.add_parser("run", help="run a task with an OpenAI-compatible model")
    run.add_argument("task")
    _add_runtime_options(run)

    resume = subparsers.add_parser("resume", help="resume a non-completed checkpoint")
    resume.add_argument("run_id")
    _add_runtime_options(resume)

    evaluate = subparsers.add_parser("eval", help="run a repeatable repository task suite")
    evaluate.add_argument("--tasks", type=Path, default=Path("evals/tasks.json"))
    evaluate.add_argument("--output", type=Path, default=Path(".minicode/evals"))
    evaluate.add_argument("--max-steps", type=int, default=12)
    evaluate.add_argument("--max-context-tokens", type=int, default=32_000)

    web = subparsers.add_parser("web", help="serve the local Web Console and API")
    web.add_argument("--host", default="127.0.0.1")
    web.add_argument("--port", type=int, default=8000)
    web.add_argument("--workspace", type=Path, default=Path.cwd())
    web.add_argument("--web-dist", type=Path, default=Path("web/dist"))
    web.add_argument("--demo", action="store_true", help="use a scripted model without an API key")
    return parser


def _add_runtime_options(command: argparse.ArgumentParser) -> None:
    command.add_argument("--workspace", type=Path, default=Path.cwd())
    command.add_argument("--max-steps", type=int, default=12)
    command.add_argument("--max-context-tokens", type=int, default=32_000)
    command.add_argument(
        "--yes",
        action="store_true",
        help="approve writes and commands without prompting; blocked commands remain denied",
    )


def _trace_path(workspace: Path) -> Path:
    return workspace.resolve() / ".minicode" / "traces.jsonl"


def _checkpoint_path(workspace: Path) -> Path:
    return workspace.resolve() / ".minicode" / "checkpoints.db"


async def run_demo(workspace: Path) -> int:
    readme = "README.md" if (workspace / "README.md").exists() else "pyproject.toml"
    model = FakeModelProvider(
        [
            ModelResponse(
                content="I will inspect one project file.",
                tool_calls=[
                    ToolCall(id="demo-read", name="read_file", arguments={"path": readme})
                ],
            ),
            ModelResponse(content=f"Demo completed after reading {readme}."),
        ]
    )
    runtime = AgentRuntime(
        model,
        create_default_registry(workspace),
        trace=JsonlTraceSink(_trace_path(workspace)),
        checkpoint=SqliteCheckpointStore(_checkpoint_path(workspace)),
    )
    result = await runtime.run("Inspect this repository and finish the deterministic demo.")
    print(result.output)
    print(f"run_id={result.run_id} status={result.status.value} steps={result.steps}")
    return 0 if result.status is RunStatus.COMPLETED else 1


def _load_model_configuration() -> tuple[str, str, str] | None:
    load_dotenv(dotenv_path=Path.cwd() / ".env")
    api_key = os.getenv("MINICODE_API_KEY", "")
    base_url = os.getenv("MINICODE_BASE_URL", "").strip()
    model_name = os.getenv("MINICODE_MODEL", "").strip()
    missing = [
        name
        for name, value in (
            ("MINICODE_API_KEY", api_key),
            ("MINICODE_BASE_URL", base_url),
            ("MINICODE_MODEL", model_name),
        )
        if not value
    ]
    if missing:
        print(f"Missing configuration: {', '.join(missing)}. Copy .env.example to .env.")
        return None
    return api_key, base_url, model_name


async def run_model_command(args: argparse.Namespace) -> int:
    model_configuration = _load_model_configuration()
    if model_configuration is None:
        return 2
    api_key, base_url, model_name = model_configuration

    workspace = args.workspace.resolve()
    approver = AlwaysApprover() if args.yes else ConsoleApprover()
    provider = OpenAICompatibleProvider(
        api_key=api_key,
        base_url=base_url,
        model=model_name,
    )
    try:
        runtime = AgentRuntime(
            provider,
            create_default_registry(workspace, PermissionPolicy(approver)),
            config=AgentConfig(
                max_steps=args.max_steps,
                max_context_tokens=args.max_context_tokens,
            ),
            trace=JsonlTraceSink(_trace_path(workspace)),
            checkpoint=SqliteCheckpointStore(_checkpoint_path(workspace)),
        )
        if args.command == "resume":
            try:
                result = await runtime.resume(args.run_id)
            except ValueError as exc:
                print(str(exc))
                return 2
        else:
            result = await runtime.run(args.task)
    finally:
        await provider.aclose()

    print(result.output or result.error or result.status.value)
    print(
        f"run_id={result.run_id} status={result.status.value} "
        f"steps={result.steps} tokens={result.usage.total_tokens}"
    )
    return 0 if result.status is RunStatus.COMPLETED else 1


async def run_evaluation_command(args: argparse.Namespace) -> int:
    model_configuration = _load_model_configuration()
    if model_configuration is None:
        return 2
    api_key, base_url, model_name = model_configuration
    try:
        suite = load_task_suite(args.tasks.resolve())
    except (OSError, ValueError) as exc:
        print(f"Unable to load evaluation tasks: {exc}")
        return 2

    run_name = f"{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"
    output_dir = args.output.resolve() / run_name
    provider = OpenAICompatibleProvider(
        api_key=api_key,
        base_url=base_url,
        model=model_name,
    )
    try:
        report = await EvaluationRunner(
            model=provider,
            model_name=model_name,
            suite=suite,
            output_dir=output_dir,
            config=AgentConfig(
                max_steps=args.max_steps,
                max_context_tokens=args.max_context_tokens,
            ),
        ).run()
    finally:
        await provider.aclose()

    print(
        f"evaluation model={report.model} passed={report.passed_tasks}/{report.total_tasks} "
        f"success_rate={report.success_rate:.2%}"
    )
    print(f"report={output_dir / 'report.json'}")
    return 0 if report.passed_tasks == report.total_tasks else 1


async def run_web_command(args: argparse.Namespace) -> int:
    import uvicorn

    from minicode_agent.web import RunManager, create_app

    if args.demo:
        model_name = "scripted-demo"

        def provider_factory() -> FakeModelProvider:
            return FakeModelProvider(
                [
                    ModelResponse(
                        content="I will confirm the selected workspace.",
                        tool_calls=[
                            ToolCall(
                                id="web-demo-pwd",
                                name="run_shell",
                                arguments={"command": "pwd"},
                            )
                        ],
                    ),
                    ModelResponse(
                        content=(
                            "Demo completed after confirming the workspace. "
                            "Streaming output is arriving incrementally in the Console."
                        )
                    ),
                ],
                streaming=True,
                stream_chunk_size=8,
                stream_delay_seconds=0.08,
            )

    else:
        model_configuration = _load_model_configuration()
        if model_configuration is None:
            return 2
        api_key, base_url, model_name = model_configuration

        def provider_factory() -> OpenAICompatibleProvider:
            return OpenAICompatibleProvider(
                api_key=api_key,
                base_url=base_url,
                model=model_name,
            )

    try:
        manager = RunManager(
            provider_factory,
            model_name=model_name,
            default_workspace=args.workspace,
        )
    except (OSError, ValueError) as exc:
        print(f"Invalid default workspace: {exc}")
        return 2
    app = create_app(manager, static_dir=args.web_dist)
    server = uvicorn.Server(
        uvicorn.Config(app, host=args.host, port=args.port, log_level="info")
    )
    await server.serve()
    return 0


async def async_main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "demo":
        return await run_demo(args.workspace)
    if args.command == "eval":
        return await run_evaluation_command(args)
    if args.command == "web":
        return await run_web_command(args)
    return await run_model_command(args)


def main() -> None:
    try:
        exit_code = asyncio.run(async_main())
    except KeyboardInterrupt:
        exit_code = 130
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
