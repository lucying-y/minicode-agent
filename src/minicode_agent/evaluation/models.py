"""Schemas for evaluation tasks and reports."""

from pydantic import BaseModel, Field


class EvalTask(BaseModel):
    """One isolated repository task and its deterministic verifier."""

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$")
    prompt: str = Field(min_length=1)
    files: dict[str, str] = Field(min_length=1)
    verify_command: str = Field(min_length=1)
    verify_timeout_seconds: int = Field(default=30, ge=1, le=120)


class EvalTaskSuite(BaseModel):
    """Versioned collection of evaluation tasks."""

    version: int = 1
    tasks: list[EvalTask] = Field(min_length=1)


class EvalResult(BaseModel):
    """Metrics and verification evidence for one task."""

    task_id: str
    run_id: str
    runtime_status: str
    passed: bool
    steps: int
    input_tokens: int
    output_tokens: int
    duration_ms: float
    verify_exit_code: int | None
    verification_output: str
    error: str | None = None


class EvalReport(BaseModel):
    """Aggregate metrics for one model and task suite run."""

    model: str
    started_at: str
    finished_at: str
    total_tasks: int
    passed_tasks: int
    success_rate: float
    results: list[EvalResult]

