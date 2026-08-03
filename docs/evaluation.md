# Evaluation

The evaluator measures whether a model-driven run leaves a repository in a verifiably correct state.
It does not treat a confident final answer as evidence of success.

## Task format

`evals/tasks.json` contains a versioned list of tasks. Every task defines:

- a stable ID;
- the user prompt;
- the initial repository files;
- a deterministic verification command and timeout.

The runner creates a separate workspace for each task, executes the normal Runtime with automatic
approval inside that disposable directory, and then runs the verifier. It records runtime status and
verification status independently: a task may pass even when the model hits a terminal limit after
making the correct edit, or fail despite the model claiming completion.

## Metrics

`report.json` records:

- verified success rate;
- model and runtime terminal status;
- model steps;
- input and output Tokens reported by the provider;
- end-to-end duration;
- verifier exit code and bounded output;
- links through `run_id` to JSONL traces and SQLite checkpoints.

Run the same task-suite version when comparing prompts, models, or Runtime changes. Preserve the raw
reports used for resume numbers.

## Trust boundary

Verification commands and model-generated shell commands execute with the current user's OS
permissions. The workspace path policy does not sandbox shell processes. Only evaluate trusted task
files locally; use a disposable container before accepting external suites.
