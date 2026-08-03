# Resume and interview notes

Only claim behavior that is present in the repository and backed by tests or an evaluation report.

## Draft project bullets

- Independently designed and implemented a lightweight coding-agent runtime with a bounded
  model-tool loop, structured stop states, and provider-neutral model and tool interfaces.
- Built a Pydantic/JSON Schema tool registry for repository reading, search, exact editing, and
  shell execution; enforced workspace path boundaries, risk levels, and explicit approval for
  state-changing operations.
- Added deterministic context budgeting that keeps complete assistant/tool blocks, plus append-only
  JSONL traces covering model usage, tool results, duration, errors, and terminal run status.
- Persisted the last consistent execution state in SQLite, retaining the run ID, cumulative usage,
  complete messages, and trace sequence so limited or failed runs can resume without replaying
  completed steps.
- Implemented an OpenAI-compatible provider and CLI, using mocked HTTP responses and a Fake Provider
  to test the complete runtime without external API dependencies.

Add benchmark numbers only after running the planned evaluation harness with a real model. Do not
reuse scores from reference projects.

## Likely interview questions

1. Why use a custom loop instead of LangGraph or another framework?
2. How do you prevent a path such as `../secret.txt` or a symlink from escaping the workspace?
3. Why preserve assistant/tool messages as a block during context trimming?
4. What can bypass an application-level command deny list, and how would Docker change the threat
   model?
5. How does the Fake Provider make failure paths deterministic?
6. Why is a checkpoint saved only after a complete model/tool boundary rather than after every tool?
