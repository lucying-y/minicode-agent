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

export type Run = {
  run_id: string;
  source: "cli" | "web";
  mode: "task" | "chat";
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
};
