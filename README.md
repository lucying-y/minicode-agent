# MiniCode Agent

[English](README.md) | [简体中文](README.zh-CN.md)

MiniCode Agent is a small, inspectable coding-agent runtime for repository tasks. It is an
independent implementation focused on the engineering behind an agent: control flow, structured
tools, context limits, permissions, provider adaptation, and execution traces.

The project takes architectural inspiration from
[mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent),
[teenycode](https://github.com/yangshun/teenycode), and
[learn-claude-code](https://github.com/shareAI-lab/learn-claude-code). It does not depend on or copy
an agent framework.

## Current capabilities

- Bounded model-tool loop with step, total-token, and context limits.
- Provider-neutral messages plus an OpenAI-compatible chat-completions adapter.
- Pydantic tool arguments exposed to models as JSON Schema.
- Workspace-scoped `read_file`, `list_files`, `search_text`, `edit_file`, and `run_shell` tools.
- Read/write/execute permission levels and human approval for state-changing operations.
- Exact, unique text replacement to make edits predictable and reviewable.
- Append-only JSONL traces for model responses, tool results, usage, timing, and terminal status.
- SQLite checkpoints that preserve consistent messages, cumulative usage, and trace sequence.
- A workspace-local SQLite run store shared by CLI and Web timelines across processes.
- A persistent interactive CLI session with multi-turn context and slash commands.
- Repeatable repository-task evaluation with deterministic verification and JSON metric reports.
- Deterministic Fake Provider for offline testing and demos.
- Local React Web Console with FastAPI, SSE event updates, browser approvals, active cancellation,
  and checkpoint resume.
- Cancellation during model requests, pending approvals, and shell execution, plus persisted CLI
  interruption state on `Ctrl+C`.

## Quick start

Python 3.12+ and [uv](https://docs.astral.sh/uv/) are required. The Web Console also requires
Node.js 20.19+ (Node.js 22 LTS is recommended). macOS, Linux, and native Windows PowerShell are
supported.

```bash
uv sync --all-groups
uv run minicode demo --workspace .
```

The demo does not call an external model. It performs a scripted tool call, writes its readable
trace to `.minicode/traces.jsonl`, and records its timeline in `.minicode/runs.db`.

### Native Windows PowerShell

Windows 10/11 works without WSL or Git Bash. MiniCode prefers PowerShell 7 (`pwsh.exe`) and falls
back to Windows PowerShell 5.1 (`powershell.exe`). Shell tool calls, the Web demo, and evaluation
verification all use that explicit backend instead of an implicit `cmd.exe` parent shell.

Run the initial setup from PowerShell:

```powershell
git clone https://github.com/anqi399/minicode-agent.git
Set-Location minicode-agent
uv sync --all-groups

Set-Location web
npm ci
npm run build
Set-Location ..

Copy-Item .env.example .env
notepad .env
```

Then start either surface with a native Windows path:

```powershell
uv run minicode chat --workspace "C:\Users\damon\projects\demo"
uv run minicode web --workspace "C:\Users\damon\projects\demo" --port 8000
```

PowerShell output is normalized to UTF-8, paths with spaces or non-ASCII characters are supported,
and a timed-out command terminates its process tree. Commands still run with the current Windows
user's permissions, so approvals and the deny list must not be treated as an OS sandbox.

### Web Console

Build the frontend once, then start the local console with the scripted provider:

```bash
cd web
npm ci
npm run build
cd ..
uv run minicode web --demo --workspace /path/to/repo
```

Open <http://127.0.0.1:8000>. The demo uses no API tokens and pauses before its shell command so the
browser approval and streaming-output flows can be exercised. Run
`uv run minicode web --workspace /path/to/repo` instead to use the model configured in `.env`. See
[the Chinese Web Console guide](docs/web-console.zh-CN.md) for the UI, API, lifecycle, and persistence
details. The configured default workspace is editable for each new run.

The console also lists runs started later from the CLI when both commands use the same workspace.
CLI runs are view-only in the browser: approvals and resume operations remain in the terminal.

The port is not tied to the provider mode. To keep demo and real-model consoles running together,
use different free ports, for example `8000` for `--demo` and `8001` for the `.env` model.

## Configure a model

Copy the example environment file and fill in an OpenAI-compatible endpoint:

```bash
cp .env.example .env
```

```dotenv
MINICODE_API_KEY=your-api-key
MINICODE_BASE_URL=https://your-provider.example/v1
MINICODE_MODEL=your-model-name
```

The API key is loaded from the local `.env`, which is ignored by Git. It is never expected in source
files or command-line arguments.

### Interactive CLI

From the repository you want the agent to work on, enter a persistent session with `minicode chat`.
Running `minicode` without a subcommand does the same thing:

```bash
uv run minicode chat --workspace /path/to/repo
```

Each message keeps the same `run_id`, model history, cumulative token usage, approvals, checkpoint,
and Web timeline. `--max-steps` is the per-message model-step limit in chat mode. Available commands
are `/help`, `/status`, `/history`, `/clear`, `/exit`, and `/quit`; bare `exit` and `quit` also close
the session. `/clear` closes the current run and starts a new one with empty context.

To use the shorter `minicode` command from any current directory, install this checkout once:

```bash
uv tool install -e .
cd /path/to/repo
minicode
```

The installed command reads `MINICODE_*` from the shell environment or a `.env` in the directory
where it is launched.

Run a repository task:

```bash
uv run minicode run "Inspect the project and fix the failing tests" --workspace /path/to/repo
```

File writes and shell commands require confirmation. `--yes` skips interactive confirmation for
trusted tasks, but commands matching the built-in high-risk deny list remain blocked.

Each run prints a `run_id`. A run stopped by a step limit, token limit, tool error, or provider error
can continue from its last consistent model/tool boundary after raising the relevant limit or fixing
the external problem:

```bash
uv run minicode resume RUN_ID --workspace /path/to/repo --max-steps 24
```

Checkpoints are stored in `.minicode/checkpoints.db`. Shared CLI/Web timeline summaries and events
are stored in `.minicode/runs.db`. Completed runs are intentionally immutable and cannot be resumed.

## Evaluation

After configuring a model, run the bundled three-task suite:

```bash
uv run minicode eval --tasks evals/tasks.json
```

Each invocation creates a new `.minicode/evals/<timestamp>-<id>/` directory containing:

- the isolated workspace produced for every task;
- the full JSONL trajectory and SQLite checkpoint for each run;
- a `report.json` with pass/fail, runtime status, steps, input/output tokens, and elapsed time.

Success is determined by each task's verification command rather than the model's final message. A
non-perfect suite exits with status 1. Evaluation files can contain executable verification commands;
only run task suites you trust, preferably inside a disposable container.

### Verified baseline

On 2026-08-03, `gpt-5.6-sol` passed all 3 bundled repository tasks through the real provider path:

| Result | Average steps | Total Tokens | Total duration |
| --- | ---: | ---: | ---: |
| 3/3 verified | 5 | 18,415 | 106.14s |

Every run reached `completed`, and every independent verifier exited with code 0. The raw aggregate
and per-task metrics are preserved in
[`benchmarks/gpt-5.6-sol-baseline-20260803.json`](benchmarks/gpt-5.6-sol-baseline-20260803.json).
This is a small, self-authored regression suite, not a claim about performance on SWE-bench or other
public benchmarks.

## Execution flow

```text
Task
  -> context manager
  -> model provider
  -> zero or more structured tool calls
  -> schema validation
  -> permission policy
  -> workspace tool execution
  -> tool observations appended to history
  -> next model step or terminal status
```

The runtime retains the complete in-memory trajectory. Before each model request, the context
manager preserves the system prompt, original task, and newest complete assistant/tool blocks that
fit within the configured budget. This avoids sending a tool result without its originating call.

## Safety boundary

The path checks, command deny list, and approval prompts are application-level controls. They are
not an operating-system sandbox and can never make arbitrary model-generated shell commands fully
safe. Use a disposable container or virtual machine for untrusted repositories and tasks.

## Development

```bash
uv run ruff check .
uv run pytest --cov
```

Tests use temporary workspaces, mocked HTTP responses, and a deterministic model. They cover the
agent loop, limits, context selection, path escape prevention, approvals, file tools, command
failure/timeout behavior, checkpoint recovery, provider translation, CLI demo, repository-task
evaluation, interactive multi-turn context, and JSONL event ordering.

## Structure

```text
src/minicode_agent/
├── runtime/       # agent loop, state types, context budgeting
├── models/        # provider protocol, fake model, OpenAI-compatible adapter
├── tools/         # schemas, registry, filesystem and shell tools
├── security/      # workspace boundary and permission policy
├── persistence/   # JSONL traces, SQLite checkpoints, and the shared run timeline store
├── evaluation/    # task schemas, isolated execution, verification, reports
├── web/           # FastAPI app, persisted run manager, SSE and browser approval
└── cli.py         # demo and real-model commands
web/               # React, TypeScript and Vite console
```

## Deliberate limitations

- The provider targets OpenAI-compatible `/chat/completions` and streams standard SSE deltas; it does
  not support provider-specific protocols.
- Context usage is estimated from serialized character length, not a provider tokenizer.
- The Web Console discovers persisted history only in its configured workspace and workspaces used
  by Web runs during that server process. Existing JSONL traces are not backfilled into `runs.db`.
- Web cancellation controls only tasks owned by the current server process and cannot roll back file
  changes or other side effects that already completed.
- There is no Git diff view, container sandbox, multi-user authentication, MCP, or sub-agent
  orchestration yet.

## Roadmap

1. Expand evaluation tasks and compare multiple model/configuration combinations.
2. Add structured Git diff and test-result views.
3. Add an isolated Docker execution environment.
