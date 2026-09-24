"""在隔离的评测目录中执行编码任务。

评测器有意放在 Runtime 之外。它负责准备 fixture、执行 Agent、运行独立校验器并写入报告。
这种分离避免模型自行宣称结果正确，也使不同 Provider 的结果可以对比。
"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from minicode_agent.evaluation.models import EvalReport, EvalResult, EvalTask, EvalTaskSuite
from minicode_agent.execution import ShellBackend, default_shell, platform_system_prompt
from minicode_agent.models.base import ModelProvider
from minicode_agent.persistence import JsonlTraceSink, SqliteCheckpointStore
from minicode_agent.runtime import AgentConfig, AgentRuntime, ToolCall
from minicode_agent.security import PermissionLevel, PermissionPolicy, Workspace
from minicode_agent.tools import create_default_registry


class EvaluationApprover:
    """批准一次性评测工作区中的操作。

    只有任务集来源可信且输出目录可随时丢弃时，自动批准才符合这里的安全假设。
    """

    async def approve(self, call: ToolCall, permission: PermissionLevel) -> bool:
        del call, permission
        return True


def load_task_suite(path: Path) -> EvalTaskSuite:
    """从磁盘加载并校验 UTF-8 JSON 任务集。"""
    return EvalTaskSuite.model_validate_json(path.read_text(encoding="utf-8"))


class EvaluationRunner:
    """顺序执行任务并写入机器可读报告。

    每个任务完成后都会重新写入报告，从而在后续任务失败时保留已经完成的部分进度。
    """

    def __init__(
        self,
        *,
        model: ModelProvider,
        model_name: str,
        suite: EvalTaskSuite,
        output_dir: Path,
        config: AgentConfig | None = None,
        shell: ShellBackend | None = None,
    ) -> None:
        self.model = model
        self.model_name = model_name
        self.suite = suite
        self.output_dir = output_dir.resolve()
        self.shell = shell or default_shell()
        self.config = config or AgentConfig(max_steps=12)

    async def run(self) -> EvalReport:
        """执行完整任务集并返回最终汇总报告。"""
        started_at = datetime.now(UTC)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        results = []
        for task in self.suite.tasks:
            result = await self._run_task(task)
            results.append(result)
            self._write_report(started_at, results)
        return self._write_report(started_at, results)

    async def _run_task(self, task: EvalTask) -> EvalResult:
        """准备单个 fixture、运行 Agent，并执行对应校验器。"""
        workspace_path = self.output_dir / task.id
        workspace_path.mkdir(parents=True, exist_ok=True)
        workspace = Workspace(workspace_path)
        self._write_fixture(workspace, task)
        runtime_config = self.config.model_copy(
            update={
                "system_prompt": platform_system_prompt(
                    self.config.system_prompt,
                    self.shell,
                    workspace.root,
                )
            }
        )

        runtime = AgentRuntime(
            self.model,
            create_default_registry(
                workspace.root,
                PermissionPolicy(EvaluationApprover()),
                self.shell,
            ),
            config=runtime_config,
            trace=JsonlTraceSink(workspace.root / ".minicode" / "traces.jsonl"),
            checkpoint=SqliteCheckpointStore(workspace.root / ".minicode" / "checkpoints.db"),
        )
        started = perf_counter()
        result = await runtime.run(task.prompt)
        verify_exit_code, verification_output = await self._verify(workspace, task)
        duration_ms = round((perf_counter() - started) * 1000, 3)
        return EvalResult(
            task_id=task.id,
            run_id=result.run_id,
            runtime_status=result.status.value,
            passed=verify_exit_code == 0,
            steps=result.steps,
            input_tokens=result.usage.input_tokens,
            output_tokens=result.usage.output_tokens,
            duration_ms=duration_ms,
            verify_exit_code=verify_exit_code,
            verification_output=verification_output,
            error=result.error,
        )

    @staticmethod
    def _write_fixture(workspace: Workspace, task: EvalTask) -> None:
        """在评测工作区中写入使用相对路径描述的任务文件。"""
        for relative_path, content in task.files.items():
            if Path(relative_path).is_absolute():
                raise ValueError(f"evaluation fixture path must be relative: {relative_path}")
            path = workspace.resolve(relative_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

    async def _verify(self, workspace: Workspace, task: EvalTask) -> tuple[int | None, str]:
        """移除覆盖率相关环境干扰后运行可信校验器。"""
        environment = os.environ.copy()
        for name in list(environment):
            if name.startswith("COV_CORE_") or name == "COVERAGE_PROCESS_START":
                environment.pop(name)
        result = await self.shell.run(
            task.verify_command,
            cwd=workspace.root,
            timeout_seconds=task.verify_timeout_seconds,
            max_chars=8_000,
            environment=environment,
        )
        return result.exit_code, result.output

    def _write_report(self, started_at: datetime, results: list[EvalResult]) -> EvalReport:
        """把当前部分结果或最终结果序列化到 ``report.json``。"""
        passed = sum(result.passed for result in results)
        report = EvalReport(
            model=self.model_name,
            started_at=started_at.isoformat(),
            finished_at=datetime.now(UTC).isoformat(),
            total_tasks=len(self.suite.tasks),
            passed_tasks=passed,
            success_rate=round(passed / len(self.suite.tasks), 4),
            results=results,
        )
        (self.output_dir / "report.json").write_text(
            json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return report
