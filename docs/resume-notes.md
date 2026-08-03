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
- Built a repeatable repository-task evaluator that creates isolated fixtures, verifies final code
  with executable acceptance checks, and reports success rate, steps, Token usage, and latency.
- Connected the real OpenAI-compatible provider and passed 3/3 tasks in the self-authored version 1
  suite with `gpt-5.6-sol`: 5 average model steps, 18,415 total Tokens, and 106.14 seconds end to end.
- Maintained 28 automated tests with 93.97% statement coverage; passed Ruff checks and built both
  wheel and source distributions with `uv build`.

The preserved baseline is in `benchmarks/gpt-5.6-sol-baseline-20260803.json`. Describe it as a
"self-authored three-task code-repair suite" rather than a public benchmark. Do not reuse scores
from reference projects.

## Likely interview questions

1. Why use a custom loop instead of LangGraph or another framework?
2. How do you prevent a path such as `../secret.txt` or a symlink from escaping the workspace?
3. Why preserve assistant/tool messages as a block during context trimming?
4. What can bypass an application-level command deny list, and how would Docker change the threat
   model?
5. How does the Fake Provider make failure paths deterministic?
6. Why is a checkpoint saved only after a complete model/tool boundary rather than after every tool?
7. Why should task success come from an external verifier rather than the model's final answer?
