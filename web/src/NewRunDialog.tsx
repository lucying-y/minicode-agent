import { AlertTriangle, FolderGit2, Play, RefreshCw, X } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { api } from "./api";
import type { ApprovalMode, CreateRunInput, Run } from "./types";
import { approvalModeLabel } from "./ui";

const approvalModes: ApprovalMode[] = ["ask", "auto", "read_only"];

export function NewRunDialog({
  open,
  defaultWorkspace,
  onClose,
  onCreated,
}: {
  open: boolean;
  defaultWorkspace: string;
  onClose: () => void;
  onCreated: (run: Run) => void;
}) {
  const [form, setForm] = useState<CreateRunInput>({
    task: "",
    workspace: defaultWorkspace,
    max_steps: 12,
    max_context_tokens: 32000,
    max_total_tokens: 100000,
    approval_mode: "ask",
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (defaultWorkspace && !form.workspace) {
      setForm((current) => ({ ...current, workspace: defaultWorkspace }));
    }
  }, [defaultWorkspace, form.workspace]);

  if (!open) return null;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      const run = await api.createRun(form);
      setForm((current) => ({ ...current, task: "" }));
      onCreated(run);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "任务创建失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <form className="new-run-modal" onSubmit={submit} onMouseDown={(event) => event.stopPropagation()}>
        <div className="modal-header">
          <div><span className="section-kicker">NEW RUN</span><h2>创建代码任务</h2></div>
          <button className="icon-button" type="button" onClick={onClose} title="关闭"><X size={18} /></button>
        </div>

        <label className="field wide-field">
          <span>任务</span>
          <textarea
            autoFocus
            rows={6}
            value={form.task}
            onChange={(event) => setForm({ ...form, task: event.target.value })}
            placeholder="例如：检查失败测试，完成最小范围修复并验证"
            required
          />
        </label>

        <label className="field wide-field">
          <span>工作区绝对路径</span>
          <div className="input-with-icon">
            <FolderGit2 size={16} />
            <input value={form.workspace} onChange={(event) => setForm({ ...form, workspace: event.target.value })} required />
          </div>
        </label>

        <fieldset className="approval-mode-field">
          <legend>审批模式</legend>
          <div className="segmented-control">
            {approvalModes.map((mode) => (
              <button
                key={mode}
                type="button"
                aria-pressed={form.approval_mode === mode}
                className={form.approval_mode === mode ? "active" : ""}
                onClick={() => setForm({ ...form, approval_mode: mode })}
              >
                {approvalModeLabel[mode]}
              </button>
            ))}
          </div>
        </fieldset>

        <div className="settings-grid">
          <label className="field"><span>最大步数</span><input type="number" min={1} max={100} step={1} value={form.max_steps} onChange={(event) => setForm({ ...form, max_steps: Number(event.target.value) })} required /></label>
          <label className="field"><span>上下文 Token</span><input type="number" min={128} max={1000000} step={1} value={form.max_context_tokens} onChange={(event) => setForm({ ...form, max_context_tokens: Number(event.target.value) })} required /></label>
          <label className="field"><span>总 Token</span><input type="number" min={1} max={10000000} step={1} value={form.max_total_tokens} onChange={(event) => setForm({ ...form, max_total_tokens: Number(event.target.value) })} required /></label>
        </div>

        {error && <div className="form-error"><AlertTriangle size={16} />{error}</div>}
        <div className="modal-actions">
          <button className="button secondary" type="button" onClick={onClose}>取消</button>
          <button className="button primary" type="submit" disabled={submitting || !form.task.trim()}>
            {submitting ? <RefreshCw className="spin" size={17} /> : <Play size={17} />}启动任务
          </button>
        </div>
      </form>
    </div>
  );
}
