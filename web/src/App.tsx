import {
  AlertTriangle,
  Bot,
  Check,
  CheckCircle2,
  ChevronRight,
  CircleDot,
  Clock3,
  Code2,
  FileCode2,
  FolderGit2,
  ListTree,
  Menu,
  MessageSquareText,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  Search,
  Settings2,
  ShieldAlert,
  TerminalSquare,
  Wrench,
  X,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import type { ConsoleEvent, CreateRunInput, Health, Run } from "./types";

const terminalStatuses = new Set([
  "completed",
  "step_limit",
  "token_limit",
  "tool_error",
  "failed",
  "cancelled",
]);

const resumableStatuses = new Set(["step_limit", "token_limit", "tool_error", "failed"]);

const statusLabel: Record<string, string> = {
  queued: "排队中",
  running: "运行中",
  waiting_approval: "等待审批",
  completed: "已完成",
  step_limit: "达到步数上限",
  token_limit: "达到 Token 上限",
  tool_error: "工具错误",
  failed: "运行失败",
  cancelled: "已取消",
};

function formatTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat("zh-CN").format(value);
}

function eventPresentation(event: ConsoleEvent) {
  const toolCall = event.data.call as { name?: string } | undefined;
  const toolCalls = event.data.tool_calls as Array<{ name?: string }> | undefined;
  switch (event.event_type) {
    case "run_queued":
      return { icon: Clock3, title: "任务已加入队列", tone: "neutral" };
    case "run_status":
      return { icon: CircleDot, title: `状态：${statusLabel[String(event.data.status)] || event.data.status}`, tone: "neutral" };
    case "run_started":
      return { icon: Play, title: "Agent 开始执行", tone: "positive" };
    case "run_resumed":
      return { icon: RotateCcw, title: "从 Checkpoint 恢复", tone: "positive" };
    case "model_response":
      return {
        icon: Bot,
        title: toolCalls?.length ? `模型请求 ${toolCalls.length} 个工具` : "模型返回最终结果",
        tone: "model",
      };
    case "approval_required":
      return { icon: ShieldAlert, title: `等待审批：${toolCall?.name || "工具"}`, tone: "warning" };
    case "approval_resolved":
      return { icon: event.data.approved ? Check : X, title: event.data.approved ? "操作已批准" : "操作已拒绝", tone: event.data.approved ? "positive" : "danger" };
    case "tool_result":
      return { icon: Wrench, title: `工具完成：${toolCall?.name || "未知工具"}`, tone: "tool" };
    case "run_finished":
      return { icon: CheckCircle2, title: `运行结束：${statusLabel[String(event.data.status)] || event.data.status}`, tone: event.data.status === "completed" ? "positive" : "danger" };
    case "model_error":
    case "web_error":
      return { icon: AlertTriangle, title: "运行发生错误", tone: "danger" };
    default:
      return { icon: Code2, title: event.event_type, tone: "neutral" };
  }
}

function pendingModelOutput(events: ConsoleEvent[]) {
  const outputs = new Map<number, { content: string; timestamp: string; eventId: number }>();
  for (const event of events) {
    const step = Number(event.data.step);
    if (!Number.isFinite(step)) continue;
    if (event.event_type === "model_output_delta" && typeof event.data.delta === "string") {
      const current = outputs.get(step);
      outputs.set(step, {
        content: `${current?.content || ""}${event.data.delta}`,
        timestamp: event.timestamp,
        eventId: event.id,
      });
    } else if (event.event_type === "model_response") {
      outputs.delete(step);
    }
  }
  const latest = [...outputs.entries()].sort((left, right) => right[1].eventId - left[1].eventId)[0];
  return latest ? { step: latest[0], ...latest[1] } : null;
}

function NewRunDialog({
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
          <div>
            <span className="section-kicker">NEW RUN</span>
            <h2>创建代码任务</h2>
          </div>
          <button className="icon-button" type="button" onClick={onClose} title="关闭">
            <X size={18} />
          </button>
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
            <input
              value={form.workspace}
              onChange={(event) => setForm({ ...form, workspace: event.target.value })}
              required
            />
          </div>
        </label>

        <div className="settings-grid">
          <label className="field">
            <span>最大步数</span>
            <input
              type="number"
              min={1}
              max={100}
              step={1}
              value={form.max_steps}
              onChange={(event) => setForm({ ...form, max_steps: Number(event.target.value) })}
              required
            />
          </label>
          <label className="field">
            <span>上下文 Token</span>
            <input
              type="number"
              min={128}
              max={1000000}
              step={1}
              value={form.max_context_tokens}
              onChange={(event) => setForm({ ...form, max_context_tokens: Number(event.target.value) })}
              required
            />
          </label>
          <label className="field">
            <span>总 Token</span>
            <input
              type="number"
              min={1}
              max={10000000}
              step={1}
              value={form.max_total_tokens}
              onChange={(event) => setForm({ ...form, max_total_tokens: Number(event.target.value) })}
              required
            />
          </label>
        </div>

        {error && <div className="form-error"><AlertTriangle size={16} />{error}</div>}

        <div className="modal-actions">
          <button className="button secondary" type="button" onClick={onClose}>取消</button>
          <button className="button primary" type="submit" disabled={submitting || !form.task.trim()}>
            {submitting ? <RefreshCw className="spin" size={17} /> : <Play size={17} />}
            启动任务
          </button>
        </div>
      </form>
    </div>
  );
}

function RunSidebar({
  runs,
  selectedId,
  open,
  onSelect,
  onClose,
}: {
  runs: Run[];
  selectedId: string | null;
  open: boolean;
  onSelect: (runId: string) => void;
  onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const filtered = runs.filter((run) =>
    `${run.task} ${run.workspace}`.toLowerCase().includes(query.toLowerCase()),
  );

  return (
    <aside className={`sidebar ${open ? "sidebar-open" : ""}`}>
      <div className="sidebar-heading">
        <span>运行记录</span>
        <span className="count-badge">{runs.length}</span>
        <button className="icon-button mobile-only" onClick={onClose} title="关闭运行列表">
          <X size={18} />
        </button>
      </div>
      <div className="search-box">
        <Search size={15} />
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索任务" />
      </div>
      <div className="run-list">
        {filtered.map((run) => (
          <button
            key={run.run_id}
            className={`run-row ${selectedId === run.run_id ? "selected" : ""}`}
            onClick={() => { onSelect(run.run_id); onClose(); }}
          >
            <div className="run-row-top">
              <span className={`status-dot status-${run.status}`} />
              <span className="run-title">{run.task}</span>
              <ChevronRight size={15} />
            </div>
            <div className="run-row-meta">
              <span>{statusLabel[run.status] || run.status}</span>
              <span>{formatTime(run.updated_at)}</span>
            </div>
          </button>
        ))}
        {!filtered.length && <div className="empty-list">暂无匹配记录</div>}
      </div>
    </aside>
  );
}

function Timeline({
  events,
  running,
  selectedEventId,
  onSelect,
}: {
  events: ConsoleEvent[];
  running: boolean;
  selectedEventId: number | null;
  onSelect: (event: ConsoleEvent) => void;
}) {
  const visibleEvents = events.filter((event) => event.event_type !== "model_output_delta");
  const liveOutput = pendingModelOutput(events);
  if (!visibleEvents.length && !liveOutput) {
    return <div className="empty-timeline"><Clock3 size={20} />等待第一个运行事件</div>;
  }
  return (
    <div className="timeline">
      {visibleEvents.map((event) => {
        const presentation = eventPresentation(event);
        const Icon = presentation.icon;
        const content = typeof event.data.content === "string" ? event.data.content : "";
        const result = event.data.result as { content?: string; is_error?: boolean } | undefined;
        return (
          <button
            key={event.id}
            className={`timeline-entry tone-${presentation.tone} ${selectedEventId === event.id ? "selected" : ""}`}
            onClick={() => onSelect(event)}
          >
            <span className="timeline-icon"><Icon size={16} /></span>
            <span className="timeline-body">
              <span className="timeline-heading">
                <strong>{presentation.title}</strong>
                <time>{formatTime(event.timestamp)}</time>
              </span>
              {content && <span className="timeline-preview">{content}</span>}
              {result?.content && <span className={`timeline-preview ${result.is_error ? "error-text" : ""}`}>{result.content}</span>}
            </span>
          </button>
        );
      })}
      {liveOutput && (
        <div className={`timeline-entry streaming-entry tone-model ${running ? "active" : ""}`} aria-live="polite">
          <span className="timeline-icon"><Bot size={16} /></span>
          <span className="timeline-body">
            <span className="timeline-heading">
              <strong>{running ? `模型正在生成 · 第 ${liveOutput.step} 步` : `模型输出中断 · 第 ${liveOutput.step} 步`}</strong>
              <time>{formatTime(liveOutput.timestamp)}</time>
            </span>
            <span className="streaming-output">{liveOutput.content}{running && <span className="streaming-cursor" />}</span>
          </span>
        </div>
      )}
    </div>
  );
}

function Inspector({
  run,
  event,
  busyApproval,
  onApproval,
}: {
  run: Run | null;
  event: ConsoleEvent | null;
  busyApproval: boolean;
  onApproval: (approved: boolean) => void;
}) {
  if (!run) {
    return <aside className="inspector"><div className="inspector-empty"><ListTree size={19} />选择一次运行</div></aside>;
  }
  const approval = run.pending_approval;
  return (
    <aside className="inspector">
      {approval && (
        <section className="approval-panel">
          <div className="approval-title"><ShieldAlert size={18} /><strong>需要操作审批</strong></div>
          <div className="approval-tool"><TerminalSquare size={15} />{approval.call.name}<span>{approval.permission}</span></div>
          <pre>{JSON.stringify(approval.call.arguments, null, 2)}</pre>
          <div className="approval-actions">
            <button className="button danger" disabled={busyApproval} onClick={() => onApproval(false)}><X size={16} />拒绝</button>
            <button className="button primary" disabled={busyApproval} onClick={() => onApproval(true)}><Check size={16} />批准</button>
          </div>
        </section>
      )}

      <section className="inspector-section">
        <div className="inspector-section-title"><Settings2 size={15} />运行配置</div>
        <dl className="definition-list">
          <div><dt>工作区</dt><dd title={run.workspace}>{run.workspace}</dd></div>
          <div><dt>最大步数</dt><dd>{run.max_steps}</dd></div>
          <div><dt>上下文</dt><dd>{formatNumber(run.max_context_tokens)}</dd></div>
          <div><dt>总 Token</dt><dd>{formatNumber(run.max_total_tokens)}</dd></div>
          <div><dt>Run ID</dt><dd className="mono">{run.run_id}</dd></div>
        </dl>
      </section>

      <section className="inspector-section event-inspector">
        <div className="inspector-section-title"><Code2 size={15} />事件详情</div>
        {event ? (
          <>
            <div className="event-name">{event.event_type}<span>#{event.id}</span></div>
            <pre>{JSON.stringify(event.data, null, 2)}</pre>
          </>
        ) : <div className="inspector-empty compact">选择时间线事件</div>}
      </section>
    </aside>
  );
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [events, setEvents] = useState<ConsoleEvent[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<ConsoleEvent | null>(null);
  const [newRunOpen, setNewRunOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [approvalBusy, setApprovalBusy] = useState(false);

  const selectedRun = useMemo(
    () => runs.find((run) => run.run_id === selectedId) || null,
    [runs, selectedId],
  );

  const refreshRuns = useCallback(async () => {
    const nextRuns = await api.listRuns();
    setRuns(nextRuns);
    setSelectedId((current) => current || nextRuns[0]?.run_id || null);
  }, []);

  useEffect(() => {
    Promise.all([api.health(), api.listRuns()])
      .then(([nextHealth, nextRuns]) => {
        setHealth(nextHealth);
        setRuns(nextRuns);
        setSelectedId(nextRuns[0]?.run_id || null);
        setNewRunOpen(nextRuns.length === 0);
      })
      .catch((reason) => setError(reason instanceof Error ? reason.message : "Console 初始化失败"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setEvents([]);
      setSelectedEvent(null);
      return;
    }
    let disposed = false;
    setSelectedEvent(null);
    setEvents([]);
    api.getEvents(selectedId).then((history) => {
      if (!disposed) {
        setEvents((current) => {
          const merged = new Map([...history, ...current].map((event) => [event.id, event]));
          return [...merged.values()].sort((left, right) => left.id - right.id);
        });
      }
    }).catch((reason) => setError(reason instanceof Error ? reason.message : "事件加载失败"));

    const source = new EventSource(`/api/runs/${selectedId}/events`);
    source.onmessage = (message) => {
      const event = JSON.parse(message.data) as ConsoleEvent;
      setEvents((current) => current.some((item) => item.id === event.id) ? current : [...current, event]);
      if (event.event_type === "model_output_delta") {
        setRuns((current) => current.map((run) => run.run_id === selectedId ? {
          ...run,
          event_count: Math.max(run.event_count, event.id),
          updated_at: event.timestamp,
        } : run));
        return;
      }
      void Promise.all([api.getRun(selectedId), api.listRuns()]).then(([detail, nextRuns]) => {
        if (disposed) return;
        setRuns(nextRuns.map((run) => run.run_id === detail.run_id ? detail : run));
      });
    };
    source.onerror = () => {
      if (!disposed) void refreshRuns();
    };
    return () => {
      disposed = true;
      source.close();
    };
  }, [selectedId, refreshRuns]);

  async function resolveApproval(approved: boolean) {
    if (!selectedRun?.pending_approval) return;
    setApprovalBusy(true);
    setError("");
    try {
      await api.resolveApproval(selectedRun.run_id, selectedRun.pending_approval.approval_id, approved);
      await refreshRuns();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "审批提交失败");
    } finally {
      setApprovalBusy(false);
    }
  }

  async function resume() {
    if (!selectedRun) return;
    setError("");
    try {
      const resumed = await api.resumeRun(selectedRun);
      setRuns((current) => current.map((run) => run.run_id === resumed.run_id ? resumed : run));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "恢复失败");
    }
  }

  function handleCreated(run: Run) {
    setRuns((current) => [run, ...current]);
    setSelectedId(run.run_id);
    setNewRunOpen(false);
  }

  return (
    <div className={`app-shell ${selectedRun?.pending_approval ? "has-pending-approval" : ""}`}>
      <header className="topbar">
        <div className="brand-group">
          <button className="icon-button mobile-only" onClick={() => setSidebarOpen(true)} title="打开运行列表"><Menu size={19} /></button>
          <div className="brand-mark"><Bot size={19} /></div>
          <div className="brand-name">MiniCode <span>Console</span></div>
        </div>
        <div className="topbar-actions">
          <div className={`connection-state ${health ? "online" : "offline"}`}>
            <span />{health?.model || (loading ? "连接中" : "未连接")}
          </div>
          <button className="icon-button" onClick={() => void refreshRuns()} title="刷新运行"><RefreshCw size={17} /></button>
          <button className="button primary" onClick={() => setNewRunOpen(true)}><Plus size={17} />新任务</button>
        </div>
      </header>

      {error && <div className="global-error"><AlertTriangle size={16} /><span>{error}</span><button onClick={() => setError("")} title="关闭"><X size={15} /></button></div>}

      <div className="workspace-shell">
        <RunSidebar runs={runs} selectedId={selectedId} open={sidebarOpen} onSelect={setSelectedId} onClose={() => setSidebarOpen(false)} />

        <main className="run-workspace">
          {selectedRun ? (
            <>
              <div className="run-header">
                <div className="run-heading">
                  <div className="run-status-line">
                    <span className={`status-chip status-${selectedRun.status}`}><span />{statusLabel[selectedRun.status] || selectedRun.status}</span>
                    <span className="workspace-path"><FolderGit2 size={14} />{selectedRun.workspace}</span>
                  </div>
                  <h1>{selectedRun.task}</h1>
                </div>
                {resumableStatuses.has(selectedRun.status) && (
                  <button className="button secondary" onClick={() => void resume()}><RotateCcw size={16} />恢复运行</button>
                )}
              </div>

              <div className="metrics-strip">
                <div><span>状态</span><strong>{statusLabel[selectedRun.status] || selectedRun.status}</strong></div>
                <div><span>模型步数</span><strong>{selectedRun.steps}<small> / {selectedRun.max_steps}</small></strong></div>
                <div><span>输入 Token</span><strong>{formatNumber(selectedRun.input_tokens)}</strong></div>
                <div><span>输出 Token</span><strong>{formatNumber(selectedRun.output_tokens)}</strong></div>
                <div><span>事件</span><strong>{selectedRun.event_count}</strong></div>
              </div>

              <div className="timeline-header"><MessageSquareText size={16} /><span>执行时间线</span>{!terminalStatuses.has(selectedRun.status) && <span className="live-indicator">LIVE</span>}</div>
              <Timeline
                events={events}
                running={!terminalStatuses.has(selectedRun.status)}
                selectedEventId={selectedEvent?.id || null}
                onSelect={setSelectedEvent}
              />
            </>
          ) : (
            <div className="empty-workspace">
              <div className="empty-workspace-icon"><FileCode2 size={24} /></div>
              <h1>暂无运行任务</h1>
              <button className="button primary" onClick={() => setNewRunOpen(true)}><Plus size={17} />创建任务</button>
            </div>
          )}
        </main>

        <Inspector run={selectedRun} event={selectedEvent} busyApproval={approvalBusy} onApproval={(approved) => void resolveApproval(approved)} />
      </div>

      <NewRunDialog open={newRunOpen} defaultWorkspace={health?.default_workspace || ""} onClose={() => setNewRunOpen(false)} onCreated={handleCreated} />
      {sidebarOpen && <div className="sidebar-scrim" onClick={() => setSidebarOpen(false)} />}
    </div>
  );
}
