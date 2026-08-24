"""Derive structured test results from shell tool events."""

import re
from typing import Any, Literal

from pydantic import BaseModel


class TestResult(BaseModel):
    """One recognized test command and its summarized result."""

    command: str
    status: Literal["passed", "failed", "timed_out"]
    exit_code: int | None
    duration_ms: float | None
    passed: int | None = None
    failed: int | None = None
    skipped: int | None = None
    output_excerpt: str


_TEST_COMMANDS = (
    "pytest",
    "unittest",
    "npm test",
    "npm run test",
    "pnpm test",
    "yarn test",
    "vitest",
    "jest",
    "cargo test",
    "go test",
    "dotnet test",
    "mvn test",
    "mvnw test",
    "gradle test",
    "gradlew test",
)


def extract_test_result(event_data: dict[str, Any]) -> TestResult | None:
    """Return a test result when a tool_result contains a recognized test command."""
    call = event_data.get("call", {})
    result = event_data.get("result", {})
    if call.get("name") != "run_shell":
        return None
    command = str(call.get("arguments", {}).get("command", "")).strip()
    normalized = " ".join(command.casefold().replace("\\", "/").split())
    if not any(marker in normalized for marker in _TEST_COMMANDS):
        return None

    metadata = result.get("metadata", {})
    output = str(result.get("content", ""))
    timed_out = bool(metadata.get("timed_out"))
    exit_code = metadata.get("exit_code")
    counts = _parse_counts(output)
    failed = None
    if "failed" in counts or "error" in counts:
        failed = counts.get("failed", 0) + counts.get("error", 0)
    return TestResult(
        command=command,
        status="timed_out" if timed_out else ("passed" if exit_code == 0 else "failed"),
        exit_code=exit_code if isinstance(exit_code, int) else None,
        duration_ms=(
            float(metadata["duration_ms"]) if metadata.get("duration_ms") is not None else None
        ),
        passed=counts.get("passed"),
        failed=failed,
        skipped=counts.get("skipped"),
        output_excerpt=output[-4_000:],
    )


def _parse_counts(output: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for amount, label in re.findall(
        r"(?<![\w.])(\d+)\s+(passed|failed|skipped|errors?|xfailed|xpassed)\b",
        output.casefold(),
    ):
        key = "error" if label.startswith("error") else label
        counts[key] = max(counts.get(key, 0), int(amount))
    return counts
