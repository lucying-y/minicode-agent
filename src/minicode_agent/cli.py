"""Command-line entry point for MiniCode Agent."""

import argparse
import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

from minicode_agent.artifacts import WorkspaceChangeTracker
from minicode_agent.evaluation import EvaluationRunner, load_task_suite
from minicode_agent.execution import (
    ShellBackend,
    ShellUnavailableError,
    default_shell,
    platform_system_prompt,
)
from minicode_agent.models import FakeModelProvider, OpenAICompatibleProvider
from minicode_agent.persistence import (
    JsonlTraceSink,
    PersistentRunRecorder,
    SessionReplay,
    SqliteCheckpointStore,
    SqliteRunStore,
)
from minicode_agent.runtime import (
    AgentConfig,
    AgentHarness,
    AgentPreset,
    AgentRuntime,
    ModelResponse,
    RunResult,
    RunStatus,
    ToolCall,
    get_preset,
)
from minicode_agent.security import (
    ApprovalHandler,
    ApprovalMode,
    PermissionLevel,
    PermissionPolicy,
    Workspace,
)
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


class RecordingApprover:
    """Record surface-neutral approval events around another approver."""

    def __init__(self, delegate: ApprovalHandler, store: SqliteRunStore, run_id: str) -> None:
        self.delegate = delegate
        self.store = store
        self.run_id = run_id

    async def approve(self, call: ToolCall, permission: PermissionLevel) -> bool:
        approval_id = uuid4().hex
        created_at = datetime.now(UTC).isoformat()
        self.store.append_event(
            self.run_id,
            "approval_required",
            {
                "approval_id": approval_id,
                "call": call.model_dump(mode="json"),
                "permission": permission.value,
                "created_at": created_at,
            },
        )
        approved = await self.delegate.approve(call, permission)
        self.store.append_event(
            self.run_id,
            "approval_resolved",
            {"approval_id": approval_id, "approved": approved},
        )
        return approved


class ConsoleDeltaWriter:
    """Persist model deltas while displaying them once in an interactive terminal."""

    def __init__(self, recorder: PersistentRunRecorder) -> None:
        self.recorder = recorder
        self.current_step: int | None = None
        self.printed = False

    def begin_turn(self) -> None:
        self.current_step = None
        self.printed = False

    def on_model_delta(self, run_id: str, step: int, delta: str) -> None:
        self.recorder.on_model_delta(run_id, step, delta)
        if self.current_step is not None and self.current_step != step and self.printed:
            print()
        self.current_step = step
        self.printed = True
        print(delta, end="", flush=True)

    def finish_turn(self, result: RunResult) -> None:
        self.recorder.flush_model_delta()
        if self.printed:
            print()
        elif result.output:
            print(result.output)
        elif result.error:
            print(result.error)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="minicode", description="A small coding-agent runtime")
    subparsers = parser.add_subparsers(dest="command")

    chat = subparsers.add_parser("chat", help="enter a persistent interactive coding session")
    _add_runtime_options(chat)

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
    web.add_argument("--web-dist", type=Path, default=_default_web_dist())
    web.add_argument("--demo", action="store_true", help="use a scripted model without an API key")
    return parser


def _add_runtime_options(command: argparse.ArgumentParser) -> None:
    command.add_argument("--workspace", type=Path, default=Path.cwd())
    command.add_argument("--max-steps", type=int, default=12)
    command.add_argument("--max-context-tokens", type=int, default=32_000)
    command.add_argument("--max-total-tokens", type=int, default=100_000)
    command.add_argument(
        "--preset",
        choices=[preset.value for preset in AgentPreset],
        default=AgentPreset.STANDARD.value,
        help="select a named capability set and its context constraints",
    )
    approval = command.add_mutually_exclusive_group()
    approval.add_argument(
        "--approval-mode",
        choices=[mode.value for mode in ApprovalMode],
        default=ApprovalMode.ASK.value,
        help="ask before changes, auto-approve allowed changes, or enforce read-only tools",
    )
    approval.add_argument(
        "--yes",
        action="store_true",
        help="alias for --approval-mode auto; blocked commands remain denied",
    )


def _approval_mode(args: argparse.Namespace) -> ApprovalMode:
    return ApprovalMode.AUTO if args.yes else ApprovalMode(args.approval_mode)


def _record_workspace_changes(
    store: SqliteRunStore,
    run_id: str,
    tracker: WorkspaceChangeTracker,
    *,
    reset: bool = False,
) -> None:
    store.append_event(
        run_id,
        "workspace_changes",
        tracker.collect(reset=reset).model_dump(mode="json"),
    )


def _trace_path(workspace: Path) -> Path:
    return workspace.resolve() / ".minicode" / "traces.jsonl"


def _checkpoint_path(workspace: Path) -> Path:
    return workspace.resolve() / ".minicode" / "checkpoints.db"


def _default_web_dist() -> Path:
    return Path(__file__).resolve().parents[2] / "web" / "dist"


def _agent_config(
    workspace: Path,
    shell: ShellBackend,
    *,
    max_steps: int = 12,
    max_context_tokens: int = 32_000,
    max_total_tokens: int = 100_000,
) -> AgentConfig:
    config = AgentConfig(
        max_steps=max_steps,
        max_context_tokens=max_context_tokens,
        max_total_tokens=max_total_tokens,
    )
    return config.model_copy(
        update={
            "system_prompt": platform_system_prompt(
                config.system_prompt,
                shell,
                workspace,
            )
        }
    )


async def run_demo(workspace: Path) -> int:
    workspace = Workspace(workspace).root
    shell = default_shell()
    task = "Inspect this repository and finish the deterministic demo."
    config = _agent_config(workspace, shell)
    run_id = uuid4().hex
    store = SqliteRunStore(workspace)
    store.create_run(
        run_id=run_id,
        source="cli",
        task=task,
        model_name="scripted-demo",
        config=config.model_dump(),
    )
    store.append_event(run_id, "run_queued", {"task": task})
    recorder = PersistentRunRecorder(JsonlTraceSink(_trace_path(workspace)), store)
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
    runtime = AgentHarness(
        model=model,
        tools=create_default_registry(workspace, shell=shell),
        config=config,
        trace=recorder,
        checkpoint=SqliteCheckpointStore(_checkpoint_path(workspace)),
    ).build_runtime(on_model_delta=recorder.on_model_delta)
    result = await runtime.run(task, run_id=run_id)
    recorder.flush_model_delta()
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

    workspace = Workspace(args.workspace).root
    shell = default_shell()
    config = _agent_config(
        workspace,
        shell,
        max_steps=args.max_steps,
        max_context_tokens=args.max_context_tokens,
        max_total_tokens=args.max_total_tokens,
    )
    preset = get_preset(args.preset)
    config = preset.apply(config)
    checkpoint_store = SqliteCheckpointStore(_checkpoint_path(workspace))
    store = SqliteRunStore(workspace)
    approval_mode = _approval_mode(args)
    stored_config = config.model_dump() | {
        "approval_mode": approval_mode.value,
        "preset": preset.name.value,
        "tool_names": list(preset.tool_names),
    }
    if args.command == "resume":
        run_id = args.run_id
        checkpoint = checkpoint_store.load(run_id)
        if checkpoint is None:
            print(f"checkpoint not found: {run_id}")
            return 2
        if checkpoint.status == RunStatus.COMPLETED.value:
            print(f"run is already completed: {run_id}")
            return 2
        if store.get_run(run_id) is None:
            store.create_run(
                run_id=run_id,
                source="cli",
                task=checkpoint.task,
                model_name=model_name,
                config=stored_config,
                status=checkpoint.status,
            )
        store.update_config(run_id, stored_config)
        store.append_event(run_id, "run_resume_queued", {"max_steps": config.max_steps})
    else:
        run_id = uuid4().hex
        store.create_run(
            run_id=run_id,
            source="cli",
            task=args.task,
            model_name=model_name,
            config=stored_config,
        )
        store.append_event(run_id, "run_queued", {"task": args.task})

    approver = RecordingApprover(ConsoleApprover(), store, run_id)
    recorder = PersistentRunRecorder(JsonlTraceSink(_trace_path(workspace)), store)
    change_tracker = WorkspaceChangeTracker(workspace)
    provider = OpenAICompatibleProvider(
        api_key=api_key,
        base_url=base_url,
        model=model_name,
    )
    try:
        runtime = AgentHarness(
            model=provider,
            tools=create_default_registry(
                workspace,
                PermissionPolicy(approver, mode=approval_mode),
                shell,
                allowed_tools=set(preset.tool_names),
            ),
            config=config,
            trace=recorder,
            checkpoint=checkpoint_store,
        ).build_runtime(on_model_delta=recorder.on_model_delta)
        if args.command == "resume":
            try:
                result = await runtime.resume(args.run_id)
            except ValueError as exc:
                print(str(exc))
                return 2
        else:
            result = await runtime.run(args.task, run_id=run_id)
    except asyncio.CancelledError:
        runtime.cancel(run_id, reason="keyboard_interrupt")
        print("\nRun cancelled.")
        raise
    finally:
        recorder.flush_model_delta()
        await provider.aclose()
        _record_workspace_changes(store, run_id, change_tracker)

    print(result.output or result.error or result.status.value)
    print(
        f"run_id={result.run_id} status={result.status.value} "
        f"steps={result.steps} tokens={result.usage.total_tokens}"
    )
    return 0 if result.status is RunStatus.COMPLETED else 1


def _print_chat_help() -> None:
    print(
        "Commands:\n"
        "  /help             Show this help\n"
        "  /status           Show the current session state\n"
        "  /history          Show user messages in this session\n"
        "  /replay           Rebuild and show state from the Session Event Log\n"
        "  /clear            Start a new session with empty context\n"
        "  /exit, /quit      Exit MiniCode\n"
        "  exit, quit        Exit MiniCode"
    )


def _normalize_chat_input(raw: str) -> str:
    """Repair surrogate-escaped terminal bytes and remove common paste artifacts."""
    try:
        repaired = raw.encode("utf-8", errors="surrogateescape").decode(
            "utf-8", errors="replace"
        )
    except UnicodeEncodeError:
        repaired = "".join(
            "\ufffd" if 0xD800 <= ord(character) <= 0xDFFF else character
            for character in raw
        )
    repaired = repaired.replace("\x1b[200~", "").replace("\x1b[201~", "")
    return repaired.strip().lstrip("\ufeff\ufffd\u200b")


async def run_chat_command(args: argparse.Namespace) -> int:
    """Run a persistent, terminal-driven conversation in one workspace."""
    model_configuration = _load_model_configuration()
    if model_configuration is None:
        return 2
    api_key, base_url, model_name = model_configuration
    workspace = Workspace(args.workspace).root
    shell = default_shell()
    checkpoint_store = SqliteCheckpointStore(_checkpoint_path(workspace))
    store = SqliteRunStore(workspace)
    provider = OpenAICompatibleProvider(
        api_key=api_key,
        base_url=base_url,
        model=model_name,
    )
    base_config = _agent_config(
        workspace,
        shell,
        max_steps=args.max_steps,
        max_context_tokens=args.max_context_tokens,
        max_total_tokens=args.max_total_tokens,
    )
    preset = get_preset(args.preset)
    base_config = preset.apply(base_config)
    approval_mode = _approval_mode(args)

    def create_session() -> tuple[
        str,
        AgentRuntime,
        PersistentRunRecorder,
        ConsoleDeltaWriter,
        WorkspaceChangeTracker,
    ]:
        run_id = uuid4().hex
        stored_config = base_config.model_dump() | {
            "mode": "chat",
            "approval_mode": approval_mode.value,
            "preset": preset.name.value,
            "tool_names": list(preset.tool_names),
        }
        store.create_run(
            run_id=run_id,
            source="cli",
            task="Interactive CLI session",
            model_name=model_name,
            config=stored_config,
            status="idle",
        )
        recorder = PersistentRunRecorder(JsonlTraceSink(_trace_path(workspace)), store)
        approver = RecordingApprover(
            ConsoleApprover(),
            store,
            run_id,
        )
        delta_writer = ConsoleDeltaWriter(recorder)
        runtime = AgentHarness(
            model=provider,
            tools=create_default_registry(
                workspace,
                PermissionPolicy(approver, mode=approval_mode),
                shell,
                allowed_tools=set(preset.tool_names),
            ),
            config=base_config,
            trace=recorder,
            checkpoint=checkpoint_store,
        ).build_runtime(on_model_delta=delta_writer.on_model_delta)
        runtime.start_session(run_id)
        return run_id, runtime, recorder, delta_writer, WorkspaceChangeTracker(workspace)

    run_id, runtime, recorder, delta_writer, change_tracker = create_session()
    has_user_message = False
    print("MiniCode Agent")
    print(f"Workspace: {workspace}")
    print(f"Model: {model_name}")
    print(f"Preset: {preset.name.value}")
    print(f"Shell: {shell.info.display_name}")
    print(f"Run ID: {run_id}")
    print("Type /help for commands. Use /exit, /quit, exit, or quit to leave.\n")

    try:
        while True:
            try:
                raw = await asyncio.to_thread(input, "minicode> ")
            except EOFError:
                raw = "/exit"
            content = _normalize_chat_input(raw)
            if not content:
                continue
            command = content.lower()
            if command in {"/exit", "/quit", "exit", "quit"}:
                runtime.end_session(run_id)
                recorder.flush_model_delta()
                print("Session closed.")
                return 0
            if command == "/help":
                _print_chat_help()
                continue
            if command == "/status":
                checkpoint = checkpoint_store.load(run_id)
                stored = store.get_run(run_id)
                if checkpoint is None or stored is None:
                    print("Session state is unavailable.")
                    continue
                print(
                    f"run_id={run_id} status={stored.status} steps={checkpoint.steps} "
                    f"tokens={checkpoint.usage.total_tokens} messages={len(checkpoint.messages)} "
                    f"preset={preset.name.value} tools={','.join(preset.tool_names)}"
                )
                continue
            if command == "/history":
                checkpoint = checkpoint_store.load(run_id)
                user_messages = (
                    [message.content for message in checkpoint.messages if message.role == "user"]
                    if checkpoint is not None
                    else []
                )
                if not user_messages:
                    print("No user messages in this session.")
                else:
                    for index, message in enumerate(user_messages, start=1):
                        print(f"{index}. {message}")
                continue
            if command == "/replay":
                try:
                    replay = SessionReplay.project(store.list_events(run_id))
                except ValueError as exc:
                    print(f"Replay unavailable: {exc}")
                    continue
                print(
                    f"replay run_id={replay.run_id} status={replay.status} "
                    f"steps={replay.steps} tokens={replay.usage.total_tokens} "
                    f"messages={len(replay.messages)} events={replay.event_count}"
                )
                if replay.output:
                    print(f"output: {replay.output}")
                if replay.error:
                    print(f"error: {replay.error}")
                continue
            if command == "/clear":
                runtime.end_session(run_id, reason="cleared")
                recorder.flush_model_delta()
                run_id, runtime, recorder, delta_writer, change_tracker = create_session()
                has_user_message = False
                print(f"Context cleared. New Run ID: {run_id}")
                continue
            if content.startswith("/"):
                print(f"Unknown command: {content}. Use /help for available commands.")
                continue

            if not has_user_message:
                store.update_task(run_id, content)
                has_user_message = True
            delta_writer.begin_turn()
            try:
                result = await runtime.continue_conversation(
                    run_id,
                    content,
                    max_steps=args.max_steps,
                )
            except ValueError as exc:
                print(str(exc))
                continue
            delta_writer.finish_turn(result)
            _record_workspace_changes(store, run_id, change_tracker, reset=True)
            if result.usage.total_tokens >= args.max_total_tokens:
                print("[token_limit] Session limit reached; use /clear to continue.")
            elif result.status is not RunStatus.COMPLETED:
                print(f"[{result.status.value}] Continue with another message or use /clear.")
    except asyncio.CancelledError:
        runtime.cancel(run_id, reason="keyboard_interrupt")
        _record_workspace_changes(store, run_id, change_tracker, reset=True)
        print("\nSession cancelled.")
        raise
    finally:
        recorder.flush_model_delta()
        close = getattr(provider, "aclose", None)
        if close is not None:
            await close()


async def run_evaluation_command(args: argparse.Namespace) -> int:
    model_configuration = _load_model_configuration()
    if model_configuration is None:
        return 2
    api_key, base_url, model_name = model_configuration
    shell = default_shell()
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
            shell=shell,
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

    shell = default_shell()
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
                                arguments={"command": shell.demo_command},
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
            shell=shell,
        )
    except (OSError, ValueError) as exc:
        print(f"Invalid default workspace: {exc}")
        return 2
    app = create_app(manager, static_dir=args.web_dist)
    print(
        f"Runtime environment: {shell.info.operating_system}; "
        f"shell={shell.info.display_name}"
    )
    server = uvicorn.Server(
        uvicorn.Config(app, host=args.host, port=args.port, log_level="info")
    )
    await server.serve()
    return 0


async def async_main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        args = parser.parse_args(["chat"])
    try:
        if args.command == "demo":
            return await run_demo(args.workspace)
        if args.command == "eval":
            return await run_evaluation_command(args)
        if args.command == "web":
            return await run_web_command(args)
        if args.command == "chat":
            return await run_chat_command(args)
        return await run_model_command(args)
    except ShellUnavailableError as exc:
        print(f"Shell unavailable: {exc}")
        return 2


def main() -> None:
    try:
        exit_code = asyncio.run(async_main())
    except KeyboardInterrupt:
        exit_code = 130
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
