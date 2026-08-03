# MiniCode Agent

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
- Deterministic Fake Provider for offline testing and demos.

## Quick start

Python 3.12+ and [uv](https://docs.astral.sh/uv/) are required.

```bash
uv sync --all-groups
uv run minicode demo --workspace .
```

The demo does not call an external model. It performs a scripted tool call and writes its trace to
`.minicode/traces.jsonl`.

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

Checkpoints are stored in `.minicode/checkpoints.db`. Completed runs are intentionally immutable and
cannot be resumed.

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
failure/timeout behavior, provider translation, CLI demo, and JSONL event ordering.

## Structure

```text
src/minicode_agent/
├── runtime/       # agent loop, state types, context budgeting
├── models/        # provider protocol, fake model, OpenAI-compatible adapter
├── tools/         # schemas, registry, filesystem and shell tools
├── security/      # workspace boundary and permission policy
├── persistence/   # append-only JSONL traces and SQLite checkpoints
└── cli.py         # demo and real-model commands
```

## Deliberate limitations

- The provider currently targets `/chat/completions`; streaming is not implemented.
- Context usage is estimated from serialized character length, not a provider tokenizer.
- MCP, sub-agents, a web console, and benchmark evaluation are intentionally deferred until the
  single-agent runtime is stable.

## Roadmap

1. Repeatable repository-task evaluation with success, steps, tokens, and latency metrics.
2. SSE API and a small React execution console.
3. Isolated Docker execution environment.
