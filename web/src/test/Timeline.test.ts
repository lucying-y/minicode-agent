import { describe, expect, it } from "vitest";
import { groupTimelineEvents, pendingModelOutput } from "../Timeline";
import type { ConsoleEvent } from "../types";

function event(id: number, eventType: string, data: Record<string, unknown>): ConsoleEvent {
  return {
    id,
    run_id: "run-1",
    timestamp: "2026-08-24T00:00:00Z",
    event_type: eventType,
    runtime_sequence: id,
    data,
  };
}

describe("timeline projections", () => {
  it("merges streaming chunks until the final model response", () => {
    const pending = pendingModelOutput([
      event(1, "model_output_delta", { step: 2, delta: "hello " }),
      event(2, "model_output_delta", { step: 2, delta: "world" }),
    ]);
    const completed = pendingModelOutput([
      event(1, "model_output_delta", { step: 2, delta: "hello" }),
      event(2, "model_response", { step: 2, content: "hello" }),
    ]);

    expect(pending?.content).toBe("hello world");
    expect(pending?.step).toBe(2);
    expect(completed).toBeNull();
  });

  it("groups tool follow-up events and hides dedicated artifacts", () => {
    const items = groupTimelineEvents([
      event(1, "model_response", { step: 1, tool_calls: [{ name: "run_shell" }] }),
      event(2, "tool_requested", { call: { name: "run_shell" } }),
      event(3, "approval_required", { call: { name: "run_shell" } }),
      event(4, "tool_result", { call: { name: "run_shell" } }),
      event(5, "test_result", { command: "pytest" }),
      event(6, "workspace_changes", { files: [] }),
      event(7, "run_finished", { status: "completed" }),
    ]);

    expect(items).toHaveLength(2);
    expect(items[0].kind).toBe("tool-group");
    if (items[0].kind === "tool-group") expect(items[0].events).toHaveLength(4);
    expect(items[1].kind).toBe("event");
  });
});
