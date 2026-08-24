import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api";
import { NewRunDialog } from "../NewRunDialog";

vi.mock("../api", () => ({ api: { createRun: vi.fn() } }));

describe("NewRunDialog", () => {
  beforeEach(() => vi.mocked(api.createRun).mockReset());

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
});
