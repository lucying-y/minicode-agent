import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup } from "@testing-library/react";
import { api } from "../api";
import { NewRunDialog } from "../NewRunDialog";

vi.mock("../api", () => ({ api: { createRun: vi.fn() } }));

describe("NewRunDialog", () => {
  beforeEach(() => vi.mocked(api.createRun).mockReset());
  afterEach(() => cleanup());

  it("submits the selected approval mode", async () => {
    vi.mocked(api.createRun).mockResolvedValue({ run_id: "run-1" } as never);
    const onCreated = vi.fn();
    render(<NewRunDialog open defaultWorkspace="/repo" onClose={() => undefined} onCreated={onCreated} />);

    fireEvent.change(screen.getByLabelText("任务"), { target: { value: "fix tests" } });
    fireEvent.click(screen.getByRole("button", { name: "只读" }));
    fireEvent.click(screen.getByRole("button", { name: "启动任务" }));

    await waitFor(() => expect(api.createRun).toHaveBeenCalledWith(expect.objectContaining({
      task: "fix tests",
      workspace: "/repo",
      approval_mode: "read_only",
    })));
    expect(onCreated).toHaveBeenCalled();
  });

  it("submits the selected Harness preset", async () => {
    vi.mocked(api.createRun).mockResolvedValue({ run_id: "run-2" } as never);
    render(<NewRunDialog open defaultWorkspace="/repo" onClose={() => undefined} onCreated={() => undefined} />);

    fireEvent.change(screen.getByLabelText("任务"), { target: { value: "review code" } });
    fireEvent.click(screen.getByRole("button", { name: "Review" }));
    fireEvent.click(screen.getByRole("button", { name: "启动任务" }));

    await waitFor(() => expect(api.createRun).toHaveBeenCalledWith(expect.objectContaining({
      preset: "review",
    })));
  });
});
