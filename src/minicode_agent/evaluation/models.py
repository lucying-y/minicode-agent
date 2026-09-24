"""评测任务和报告的数据 Schema。

这些模型显式保存任务定义、执行指标和验证证据。模型的自然语言回答不作为通过依据；
``verify_exit_code`` 和 ``passed`` 来自独立校验器。
"""

from pydantic import BaseModel, Field


class EvalTask(BaseModel):
    """一个隔离的仓库任务及其确定性校验器。

    ``files`` 是 Agent 启动前写入新工作区的 fixture。``verify_command`` 会在任务结束后
    执行；由于它是任务集中的可执行部分，因此其来源必须可信。
    """

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
