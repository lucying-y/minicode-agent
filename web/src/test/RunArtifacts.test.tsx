import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { artifactCounts, ChangesView, TestsView } from "../RunArtifacts";
import type { ConsoleEvent } from "../types";

function event(id: number, eventType: string, data: Record<string, unknown>): ConsoleEvent {
  return { id, run_id: "run-1", timestamp: "2026-08-24T00:00:00Z", event_type: eventType, runtime_sequence: null, data };
}

const events = [
  event(1, "workspace_changes", {
    available: true,
    reason: null,
    additions: 2,
    deletions: 1,
    files: [{ path: "src/app.py", status: "modified", additions: 2, deletions: 1, binary: false, patch: "+new line" }],
  }),
  event(2, "test_result", {
    command: "uv run pytest -q",
    status: "passed",
    exit_code: 0,
    duration_ms: 1250,
    passed: 12,
    failed: 0,
    skipped: 1,
    output_excerpt: "12 passed, 1 skipped",
  }),
];

describe("run artifacts", () => {
  it("counts and renders workspace changes", () => {
    expect(artifactCounts(events)).toEqual({ changes: 1, tests: 1 });
    render(<ChangesView events={events} />);
    expect(screen.getByText("src/app.py")).toBeInTheDocument();
    expect(screen.getAllByText("+2")).toHaveLength(2);
  });

  it("renders structured test metrics", () => {
    render(<TestsView events={events} />);
    expect(screen.getByText("uv run pytest -q")).toBeInTheDocument();
    expect(screen.getByText("12 通过")).toBeInTheDocument();
    expect(screen.getByText("1.25s")).toBeInTheDocument();
  });
});
