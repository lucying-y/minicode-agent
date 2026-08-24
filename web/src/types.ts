export type Approval = {
  approval_id: string;
  call: {
    id: string;
    name: string;
    arguments: Record<string, unknown>;
  };
  permission: "read" | "write" | "execute";
  created_at: string;
};

export type ApprovalMode = "ask" | "auto" | "read_only";

export type Run = {
  run_id: string;
  source: "cli" | "web";
  mode: "task" | "chat";
  approval_mode: ApprovalMode;
  task: string;
  workspace: string;
  model_name: string;
  status: string;
  steps: number;
  input_tokens: number;
  output_tokens: number;
  output: string;
  error: string | null;
  created_at: string;
  updated_at: string;
  max_steps: number;
  max_context_tokens: number;
  max_total_tokens: number;
  event_count: number;
  pending_approval: Approval | null;
};

export type ConsoleEvent = {
  id: number;
  run_id: string;
  timestamp: string;
  event_type: string;
  runtime_sequence: number | null;
  data: Record<string, unknown>;
};

export type Health = {
  status: "ok";
  model: string;
  default_workspace: string;
  platform: "windows" | "posix";
  operating_system: string;
  shell: "powershell" | "posix";
  shell_name: string;
  shell_version: string | null;
};

export type CreateRunInput = {
  task: string;
  workspace: string;
  max_steps: number;
  max_context_tokens: number;
  max_total_tokens: number;
  approval_mode: ApprovalMode;
};

export type FileChange = {
  path: string;
  status: "added" | "modified" | "deleted";
  additions: number | null;
  deletions: number | null;
  binary: boolean;
  patch: string;
};

export type WorkspaceChanges = {
  available: boolean;
  reason: string | null;
  files: FileChange[];
  additions: number;
  deletions: number;
};

export type TestResult = {
  command: string;
  status: "passed" | "failed" | "timed_out";
  exit_code: number | null;
  duration_ms: number | null;
  passed: number | null;
  failed: number | null;
  skipped: number | null;
  output_excerpt: string;
};
