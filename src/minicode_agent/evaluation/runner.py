"""Execute coding tasks in isolated evaluation directories."""

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
    """Approve operations inside a disposable evaluation workspace."""

    async def approve(self, call: ToolCall, permission: PermissionLevel) -> bool:
        del call, permission
        return True


def load_task_suite(path: Path) -> EvalTaskSuite:
    return EvalTaskSuite.model_validate_json(path.read_text(encoding="utf-8"))


class EvaluationRunner:
    """Run tasks sequentially and write a machine-readable report."""

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
        started_at = datetime.now(UTC)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        results = []
        for task in self.suite.tasks:
            result = await self._run_task(task)
            results.append(result)
            self._write_report(started_at, results)
        return self._write_report(started_at, results)

    async def _run_task(self, task: EvalTask) -> EvalResult:
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
        for relative_path, content in task.files.items():
            if Path(relative_path).is_absolute():
                raise ValueError(f"evaluation fixture path must be relative: {relative_path}")
            path = workspace.resolve(relative_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

    async def _verify(self, workspace: Workspace, task: EvalTask) -> tuple[int | None, str]:
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
