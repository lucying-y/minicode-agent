export const terminalStatuses = new Set([
  "completed",
  "step_limit",
  "token_limit",
  "tool_error",
  "failed",
  "cancelled",
]);

export const resumableStatuses = new Set([
  "step_limit",
  "token_limit",
  "tool_error",
  "failed",
  "cancelled",
]);

export const cancellableStatuses = new Set([
  "queued",
  "running",
  "waiting_approval",
  "cancelling",
]);

export const statusLabel: Record<string, string> = {
  idle: "等待输入",
  queued: "排队中",
  running: "运行中",
  waiting_approval: "等待审批",
  cancelling: "取消中",
  completed: "已完成",
  step_limit: "达到步数上限",
  token_limit: "达到 Token 上限",
  tool_error: "工具错误",
  failed: "运行失败",
  cancelled: "已取消",
};

export const approvalModeLabel = {
  ask: "人工审批",
  auto: "自动批准允许项",
  read_only: "只读",
} as const;

export function formatTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat("zh-CN").format(value);
}
