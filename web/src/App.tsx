import {
  AlertTriangle, Bot, Check, Code2, Copy, FileCode2, Files, FlaskConical,
  FolderGit2, ListTree, Menu, MessageSquareText, Plus, RefreshCw, RotateCcw,
  Settings2, ShieldAlert, Square, TerminalSquare, X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { NewRunDialog } from "./NewRunDialog";
import { artifactCounts, ChangesView, TestsView } from "./RunArtifacts";
import { Timeline } from "./Timeline";
import type { ConsoleEvent, Health, Run } from "./types";
import {
  approvalModeLabel, cancellableStatuses, formatNumber, formatTime,
  resumableStatuses, statusLabel, terminalStatuses,
} from "./ui";

type RunView = "timeline" | "changes" | "tests";

function SourceBadge({ source }: { source: Run["source"] }) {
  return <span className={`source-badge source-${source}`}>{source.toUpperCase()}</span>;
}

function RunSidebar({
  runs, selectedId, open, onSelect, onClose,
}: {
  runs: Run[]; selectedId: string | null; open: boolean;
  onSelect: (runId: string) => void; onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const filtered = runs.filter((run) =>
    `${run.task} ${run.workspace} ${run.source} ${run.model_name}`
      .toLowerCase().includes(query.toLowerCase()),
  );
  return (
    <aside className={`sidebar ${open ? "sidebar-open" : ""}`}>
      <div className="sidebar-heading">
        <span>运行记录</span><span className="count-badge">{runs.length}</span>
        <button className="icon-button mobile-only" onClick={onClose} title="关闭运行列表"><X size={18} /></button>
      </div>
      <div className="search-box"><ListTree size={15} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索任务" /></div>
      <div className="run-list">
        {filtered.map((run) => (
          <button key={run.run_id} className={`run-row ${selectedId === run.run_id ? "selected" : ""}`} onClick={() => { onSelect(run.run_id); onClose(); }}>
            <div className="run-row-top"><span className={`status-dot status-${run.status}`} /><span className="run-title">{run.task}</span><span /></div>
            <div className="run-row-meta">
              <span><SourceBadge source={run.source} />{run.mode === "chat" && <span className="source-badge mode-chat">CHAT</span>}{statusLabel[run.status] || run.status}</span>
              <span>{formatTime(run.updated_at)}</span>
            </div>
          </button>
        ))}
        {!filtered.length && <div className="empty-list">暂无匹配记录</div>}
      </div>
    </aside>
  );
}

function Inspector({
  run, event, busyApproval, onApproval,
}: {
  run: Run | null; event: ConsoleEvent | null; busyApproval: boolean;
  onApproval: (approved: boolean) => void;
}) {
  const [copiedEventId, setCopiedEventId] = useState<number | null>(null);
  useEffect(() => setCopiedEventId(null), [event?.id]);
  async function copyEventData() {
    if (!event) return;
    await navigator.clipboard.writeText(JSON.stringify(event.data, null, 2));
    setCopiedEventId(event.id);
  }
  if (!run) return <aside className="inspector"><div className="inspector-empty"><ListTree size={19} />选择一次运行</div></aside>;
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
      {run.source === "cli" && run.status === "waiting_approval" && (
        <section className="approval-panel readonly-approval">
          <div className="approval-title"><TerminalSquare size={18} /><strong>等待终端审批</strong></div>
          <p>此任务由 CLI 发起，请回到原终端批准或拒绝操作。</p>
        </section>
      )}
      <section className="inspector-section">
        <div className="inspector-section-title"><Settings2 size={15} />运行配置</div>
        <dl className="definition-list">
          <div><dt>来源</dt><dd><SourceBadge source={run.source} /></dd></div>
          <div><dt>会话</dt><dd>{run.mode === "chat" ? "交互会话" : "单次任务"}</dd></div>
          <div><dt>审批</dt><dd>{approvalModeLabel[run.approval_mode]}</dd></div>
          <div><dt>Preset</dt><dd>{run.preset}</dd></div>
          <div><dt>工具</dt><dd title={run.tool_names.join(", ")}>{run.tool_names.length} 个</dd></div>
          <div><dt>模型</dt><dd title={run.model_name}>{run.model_name}</dd></div>
          <div><dt>工作区</dt><dd title={run.workspace}>{run.workspace}</dd></div>
          <div><dt>最大步数</dt><dd>{run.max_steps}</dd></div>
          <div><dt>上下文</dt><dd>{formatNumber(run.max_context_tokens)}</dd></div>
          <div><dt>总 Token</dt><dd>{formatNumber(run.max_total_tokens)}</dd></div>
          <div><dt>Run ID</dt><dd className="mono">{run.run_id}</dd></div>
        </dl>
      </section>
      <section className="inspector-section event-inspector">
        <div className="inspector-section-title">
          <Code2 size={15} />事件详情
          {event && <button className="icon-button event-copy-button" onClick={() => void copyEventData()} title={copiedEventId === event.id ? "已复制" : "复制事件 JSON"}>{copiedEventId === event.id ? <Check size={14} /> : <Copy size={14} />}</button>}
        </div>
        {event ? <><div className="event-name">{event.event_type}<span>#{event.id}</span></div><pre>{JSON.stringify(event.data, null, 2)}</pre></> : <div className="inspector-empty compact">选择时间线事件</div>}
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
  const [activeView, setActiveView] = useState<RunView>("timeline");
  const [newRunOpen, setNewRunOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [approvalBusy, setApprovalBusy] = useState(false);
  const [cancelBusy, setCancelBusy] = useState(false);

  const selectedRun = useMemo(() => runs.find((run) => run.run_id === selectedId) || null, [runs, selectedId]);
  const counts = useMemo(() => artifactCounts(events), [events]);
  const refreshRuns = useCallback(async () => {
    const nextRuns = await api.listRuns();
    setRuns(nextRuns);
    setSelectedId((current) => current || nextRuns[0]?.run_id || null);
  }, []);

  useEffect(() => {
    Promise.all([api.health(), api.listRuns()])
      .then(([nextHealth, nextRuns]) => {
        setHealth(nextHealth); setRuns(nextRuns); setSelectedId(nextRuns[0]?.run_id || null);
        setNewRunOpen(nextRuns.length === 0);
      })
      .catch((reason) => setError(reason instanceof Error ? reason.message : "Console 初始化失败"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    const interval = window.setInterval(() => void refreshRuns().catch((reason) => setError(reason instanceof Error ? reason.message : "运行列表刷新失败")), 2000);
    return () => window.clearInterval(interval);
  }, [refreshRuns]);

  useEffect(() => {
    if (!selectedId) { setEvents([]); setSelectedEvent(null); return; }
    let disposed = false;
    setActiveView("timeline"); setSelectedEvent(null); setEvents([]);
    api.getEvents(selectedId).then((history) => {
      if (!disposed) setEvents((current) => {
        const merged = new Map([...history, ...current].map((item) => [item.id, item]));
        return [...merged.values()].sort((left, right) => left.id - right.id);
      });
    }).catch((reason) => setError(reason instanceof Error ? reason.message : "事件加载失败"));

    const source = new EventSource(`/api/runs/${selectedId}/events`);
    source.onmessage = (message) => {
      const event = JSON.parse(message.data) as ConsoleEvent;
      setEvents((current) => current.some((item) => item.id === event.id) ? current : [...current, event]);
      if (event.event_type === "model_output_delta") {
        setRuns((current) => current.map((run) => run.run_id === selectedId ? { ...run, event_count: Math.max(run.event_count, event.id), updated_at: event.timestamp } : run));
        return;
      }
      void Promise.all([api.getRun(selectedId), api.listRuns()]).then(([detail, nextRuns]) => {
        if (!disposed) setRuns(nextRuns.map((run) => run.run_id === detail.run_id ? detail : run));
      });
    };
    source.onerror = () => { if (!disposed) void refreshRuns(); };
    return () => { disposed = true; source.close(); };
  }, [selectedId, refreshRuns]);

  async function resolveApproval(approved: boolean) {
    if (!selectedRun?.pending_approval) return;
    setApprovalBusy(true); setError("");
    try {
      await api.resolveApproval(selectedRun.run_id, selectedRun.pending_approval.approval_id, approved);
      await refreshRuns();
    } catch (reason) { setError(reason instanceof Error ? reason.message : "审批提交失败"); }
    finally { setApprovalBusy(false); }
  }

  async function resume() {
    if (!selectedRun) return;
    setError("");
    try {
      const resumed = await api.resumeRun(selectedRun);
      setRuns((current) => current.map((run) => run.run_id === resumed.run_id ? resumed : run));
    } catch (reason) { setError(reason instanceof Error ? reason.message : "恢复失败"); }
  }

  async function cancelRun() {
    if (!selectedRun || !window.confirm("确认取消当前任务？")) return;
    setCancelBusy(true); setError("");
    try {
      const cancelled = await api.cancelRun(selectedRun.run_id);
      setRuns((current) => current.map((run) => run.run_id === cancelled.run_id ? cancelled : run));
    } catch (reason) { setError(reason instanceof Error ? reason.message : "取消失败"); }
    finally { setCancelBusy(false); }
  }

  function handleCreated(run: Run) {
    setRuns((current) => [run, ...current]); setSelectedId(run.run_id); setNewRunOpen(false);
  }

  return (
    <div className={`app-shell ${selectedRun?.pending_approval ? "has-pending-approval" : ""}`}>
      <header className="topbar">
        <div className="brand-group"><button className="icon-button mobile-only" onClick={() => setSidebarOpen(true)} title="打开运行列表"><Menu size={19} /></button><div className="brand-mark"><Bot size={19} /></div><div className="brand-name">MiniCode <span>Console</span></div></div>
        <div className="topbar-actions">
          <div className={`connection-state ${health ? "online" : "offline"}`} title={health ? `${health.operating_system} · ${health.shell_name}${health.shell_version ? ` ${health.shell_version}` : ""}` : undefined}><span />{health ? `${health.model} · ${health.shell_name}` : (loading ? "连接中" : "未连接")}</div>
          <button className="icon-button" onClick={() => void refreshRuns()} title="刷新运行"><RefreshCw size={17} /></button>
          <button className="button primary" onClick={() => setNewRunOpen(true)}><Plus size={17} />新任务</button>
        </div>
      </header>
      {error && <div className="global-error"><AlertTriangle size={16} /><span>{error}</span><button onClick={() => setError("")} title="关闭"><X size={15} /></button></div>}

      <div className="workspace-shell">
        <RunSidebar runs={runs} selectedId={selectedId} open={sidebarOpen} onSelect={setSelectedId} onClose={() => setSidebarOpen(false)} />
        <main className="run-workspace">
          {selectedRun ? <>
            <div className="run-header">
              <div className="run-heading">
                <div className="run-status-line"><span className={`status-chip status-${selectedRun.status}`}><span />{statusLabel[selectedRun.status] || selectedRun.status}</span><SourceBadge source={selectedRun.source} />{selectedRun.mode === "chat" && <span className="source-badge mode-chat">CHAT</span>}<span className="source-badge">{selectedRun.preset}</span><span className="workspace-path"><FolderGit2 size={14} />{selectedRun.workspace}</span></div>
                <h1>{selectedRun.task}</h1>
              </div>
              <div className="run-actions">
                {selectedRun.source === "web" && cancellableStatuses.has(selectedRun.status) && <button className="button danger" disabled={cancelBusy || selectedRun.status === "cancelling"} onClick={() => void cancelRun()}><Square size={15} />{selectedRun.status === "cancelling" ? "取消中" : "取消任务"}</button>}
                {selectedRun.source === "web" && resumableStatuses.has(selectedRun.status) && <button className="button secondary" onClick={() => void resume()}><RotateCcw size={16} />恢复运行</button>}
              </div>
            </div>
            <div className="metrics-strip">
              <div><span>状态</span><strong>{statusLabel[selectedRun.status] || selectedRun.status}</strong></div>
              <div><span>{selectedRun.mode === "chat" ? "累计步数" : "模型步数"}</span><strong>{selectedRun.steps}{selectedRun.mode === "task" && <small> / {selectedRun.max_steps}</small>}</strong></div>
              <div><span>输入 Token</span><strong>{formatNumber(selectedRun.input_tokens)}</strong></div>
              <div><span>输出 Token</span><strong>{formatNumber(selectedRun.output_tokens)}</strong></div>
              <div><span>事件</span><strong>{selectedRun.event_count}</strong></div>
            </div>
            <div className="run-view-tabs" role="tablist" aria-label="运行详情">
              <button role="tab" aria-selected={activeView === "timeline"} className={activeView === "timeline" ? "active" : ""} onClick={() => setActiveView("timeline")}><MessageSquareText size={15} />时间线{!terminalStatuses.has(selectedRun.status) && <span className="live-indicator">LIVE</span>}</button>
              <button role="tab" aria-selected={activeView === "changes"} className={activeView === "changes" ? "active" : ""} onClick={() => setActiveView("changes")}><Files size={15} />变更<span className="tab-count">{counts.changes}</span></button>
              <button role="tab" aria-selected={activeView === "tests"} className={activeView === "tests" ? "active" : ""} onClick={() => setActiveView("tests")}><FlaskConical size={15} />测试<span className="tab-count">{counts.tests}</span></button>
            </div>
            {activeView === "timeline" && <Timeline events={events} running={!terminalStatuses.has(selectedRun.status)} selectedEventId={selectedEvent?.id || null} onSelect={setSelectedEvent} />}
            {activeView === "changes" && <ChangesView events={events} />}
            {activeView === "tests" && <TestsView events={events} />}
          </> : <div className="empty-workspace"><div className="empty-workspace-icon"><FileCode2 size={24} /></div><h1>暂无运行任务</h1><button className="button primary" onClick={() => setNewRunOpen(true)}><Plus size={17} />创建任务</button></div>}
        </main>
        <Inspector run={selectedRun} event={selectedEvent} busyApproval={approvalBusy} onApproval={(approved) => void resolveApproval(approved)} />
      </div>
      <NewRunDialog open={newRunOpen} defaultWorkspace={health?.default_workspace || ""} onClose={() => setNewRunOpen(false)} onCreated={handleCreated} />
      {sidebarOpen && <div className="sidebar-scrim" onClick={() => setSidebarOpen(false)} />}
    </div>
  );
}
