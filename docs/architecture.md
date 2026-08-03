# Architecture

MiniCode Agent separates orchestration from side effects:

```text
User task
   |
   v
Agent loop -----> Model provider
   |
   v
Tool registry --> Permission policy --> Workspace tools
   |
   v
Context manager + JSONL trace store
```

## Boundaries

- `runtime`: owns the loop, limits, state transitions, and stop conditions.
- `models`: translates messages and tool schemas to a model API.
- `tools`: validates arguments and performs workspace-scoped operations.
- `security`: decides whether a tool call is allowed, denied, or requires approval.
- `persistence`: records append-only execution events and checkpoints.
- `cli`: connects configuration and user interaction to the runtime.

Application-level path and command checks are defense-in-depth controls, not an operating-system
sandbox. Untrusted tasks should eventually run in a container or another isolated environment.

