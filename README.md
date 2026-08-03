# MiniCode Agent

MiniCode Agent is a small, inspectable coding-agent runtime for repository tasks. It is being built
from first principles as a portfolio project rather than as a wrapper around an existing agent
framework.

## Project goals

- Keep the model, runtime, tools, permissions, and persistence layers replaceable.
- Make every model decision and tool result observable in an execution trace.
- Constrain file and command tools to an explicit workspace.
- Test the agent loop offline with a deterministic fake model.
- Prefer a focused implementation that can be explained in an interview.

## Planned milestones

1. Model protocol and bounded agent loop.
2. Structured repository tools and workspace permissions.
3. Context budgeting and JSONL execution traces.
4. CLI and an OpenAI-compatible provider.
5. Repeatable evaluation tasks and a small web console.

The runtime is under active development. Commands and public APIs may change before `0.2.0`.

