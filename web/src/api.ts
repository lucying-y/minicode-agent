import type { ConsoleEvent, CreateRunInput, Health, Run, TestResult, WorkspaceChanges } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: string };
    throw new Error(body.detail || `请求失败 (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<Health>("/api/health"),
  listRuns: () => request<Run[]>("/api/runs"),
  getRun: (runId: string) => request<Run>(`/api/runs/${runId}`),
  getEvents: (runId: string) =>
    request<ConsoleEvent[]>(`/api/runs/${runId}/events/history`),
  getChanges: (runId: string) => request<WorkspaceChanges[]>(`/api/runs/${runId}/changes`),
  getTests: (runId: string) => request<TestResult[]>(`/api/runs/${runId}/tests`),
  createRun: (input: CreateRunInput) =>
    request<Run>("/api/runs", { method: "POST", body: JSON.stringify(input) }),
  resolveApproval: (runId: string, approvalId: string, approved: boolean) =>
    request<Run>(`/api/runs/${runId}/approval`, {
      method: "POST",
      body: JSON.stringify({ approval_id: approvalId, approved }),
    }),
  cancelRun: (runId: string) =>
    request<Run>(`/api/runs/${runId}/cancel`, { method: "POST" }),
  resumeRun: (run: Run) =>
    request<Run>(`/api/runs/${run.run_id}/resume`, {
      method: "POST",
      body: JSON.stringify({
        max_steps: Math.max(run.max_steps + 12, run.steps + 1),
        max_context_tokens: run.max_context_tokens,
        max_total_tokens: run.max_total_tokens,
        approval_mode: run.approval_mode,
      }),
    }),
};
