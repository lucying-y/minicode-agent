import json
from pathlib import Path

from minicode_agent.evaluation import EvalTask, EvalTaskSuite, EvaluationRunner, load_task_suite
from minicode_agent.models import FakeModelProvider
from minicode_agent.runtime import ModelResponse, RunStatus, TokenUsage, ToolCall


async def test_evaluation_runner_edits_fixture_and_records_metrics(tmp_path: Path) -> None:
    task = EvalTask(
        id="fix-value",
        prompt="Change value to 2",
        files={"app.py": "value = 1\n"},
        verify_command="python3 -c 'from app import value; assert value == 2'",
    )
    model = FakeModelProvider(
        [
            ModelResponse(
                tool_calls=[
                    ToolCall(
                        id="edit-1",
                        name="edit_file",
                        arguments={"path": "app.py", "old_text": "1", "new_text": "2"},
                    )
                ],
                usage=TokenUsage(input_tokens=10, output_tokens=4),
            ),
            ModelResponse(content="done", usage=TokenUsage(input_tokens=12, output_tokens=2)),
        ]
    )
    output_dir = tmp_path / "evaluation"
    runner = EvaluationRunner(
        model=model,
        model_name="fake-model",
        suite=EvalTaskSuite(tasks=[task]),
        output_dir=output_dir,
    )

    report = await runner.run()

    assert report.total_tasks == 1
    assert report.passed_tasks == 1
    assert report.success_rate == 1.0
    assert report.results[0].runtime_status == RunStatus.COMPLETED.value
    assert report.results[0].steps == 2
    assert report.results[0].input_tokens == 22
    assert (output_dir / "fix-value" / "app.py").read_text(encoding="utf-8") == "value = 2\n"
    saved_report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    assert saved_report["results"][0]["passed"] is True


def test_load_bundled_task_suite() -> None:
    suite = load_task_suite(Path("evals/tasks.json"))

    assert suite.version == 1
    assert [task.id for task in suite.tasks] == [
        "fix-addition",
        "implement-slugify",
        "repair-config-lookup",
    ]

