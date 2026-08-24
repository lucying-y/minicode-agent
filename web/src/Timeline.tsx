import {
  AlertTriangle, Bot, Check, CheckCircle2, CircleDot, Clock3, Code2,
  MessageSquareText, Play, RotateCcw, ShieldAlert, Square, TerminalSquare, Wrench, X,
  ChevronRight,
} from "lucide-react";
import type { ConsoleEvent } from "./types";
import { formatTime, statusLabel } from "./ui";

export function eventPresentation(event: ConsoleEvent) {
  const toolCall = event.data.call as { name?: string } | undefined;
  const toolCalls = event.data.tool_calls as Array<{ name?: string }> | undefined;
  switch (event.event_type) {
    case "run_queued": return { icon: Clock3, title: "任务已加入队列", tone: "neutral" };
    case "run_status": return { icon: CircleDot, title: `状态：${statusLabel[String(event.data.status)] || event.data.status}`, tone: "neutral" };
    case "run_cancel_requested": return { icon: Square, title: "正在取消任务", tone: "warning" };
    case "run_cancelled": return { icon: Square, title: "任务已取消", tone: "danger" };
    case "run_started": return { icon: Play, title: "Agent 开始执行", tone: "positive" };
    case "session_started": return { icon: TerminalSquare, title: "CLI 会话已启动", tone: "positive" };
    case "user_message": return { icon: MessageSquareText, title: "用户消息", tone: "model" };
    case "session_waiting_input": return { icon: Clock3, title: "等待下一条输入", tone: "neutral" };
    case "session_limit_reached": return { icon: AlertTriangle, title: "会话达到 Token 上限", tone: "warning" };
    case "session_finished": return { icon: CheckCircle2, title: "CLI 会话已退出", tone: "positive" };
    case "run_resumed": return { icon: RotateCcw, title: "从 Checkpoint 恢复", tone: "positive" };
    case "model_response": return { icon: Bot, title: toolCalls?.length ? `模型请求 ${toolCalls.length} 个工具` : "模型返回最终结果", tone: "model" };
    case "approval_required": return { icon: ShieldAlert, title: `等待审批：${toolCall?.name || "工具"}`, tone: "warning" };
    case "approval_resolved": return { icon: event.data.approved ? Check : X, title: event.data.approved ? "操作已批准" : "操作已拒绝", tone: event.data.approved ? "positive" : "danger" };
    case "tool_result": return { icon: Wrench, title: `工具完成：${toolCall?.name || "未知工具"}`, tone: "tool" };
    case "run_finished": return { icon: CheckCircle2, title: `运行结束：${statusLabel[String(event.data.status)] || event.data.status}`, tone: event.data.status === "completed" ? "positive" : "danger" };
    case "model_error":
    case "web_error": return { icon: AlertTriangle, title: "运行发生错误", tone: "danger" };
    default: return { icon: Code2, title: event.event_type, tone: "neutral" };
  }
}

export function pendingModelOutput(events: ConsoleEvent[]) {
  const outputs = new Map<number, { content: string; timestamp: string; eventId: number }>();
  for (const event of events) {
    const step = Number(event.data.step);
    if (!Number.isFinite(step)) continue;
    if (event.event_type === "model_output_delta" && typeof event.data.delta === "string") {
      const current = outputs.get(step);
      outputs.set(step, { content: `${current?.content || ""}${event.data.delta}`, timestamp: event.timestamp, eventId: event.id });
    } else if (event.event_type === "model_response") {
      outputs.delete(step);
    }
  }
  const latest = [...outputs.entries()].sort((left, right) => right[1].eventId - left[1].eventId)[0];
  return latest ? { step: latest[0], ...latest[1] } : null;
}

export type TimelineItem =
  | { kind: "event"; event: ConsoleEvent }
  | { kind: "tool-group"; events: ConsoleEvent[] };

const toolFollowUpEvents = new Set(["approval_required", "approval_resolved", "tool_result"]);

export function groupTimelineEvents(events: ConsoleEvent[]): TimelineItem[] {
  const hidden = new Set(["model_output_delta", "workspace_changes", "test_result"]);
  const visibleEvents = events.filter((event) => !hidden.has(event.event_type));
  const items: TimelineItem[] = [];
  for (let index = 0; index < visibleEvents.length;) {
    const event = visibleEvents[index];
    const toolCalls = event.data.tool_calls;
    if (event.event_type !== "model_response" || !Array.isArray(toolCalls) || !toolCalls.length) {
      items.push({ kind: "event", event });
      index += 1;
      continue;
    }
    const groupedEvents = [event];
    index += 1;
    while (index < visibleEvents.length && toolFollowUpEvents.has(visibleEvents[index].event_type)) {
      groupedEvents.push(visibleEvents[index]);
      index += 1;
    }
    items.push({ kind: "tool-group", events: groupedEvents });
  }
  return items;
}

function TimelineEvent({ event, selected, onSelect }: { event: ConsoleEvent; selected: boolean; onSelect: (event: ConsoleEvent) => void }) {
  const presentation = eventPresentation(event);
  const Icon = presentation.icon;
  const content = typeof event.data.content === "string" ? event.data.content : "";
  const result = event.data.result as { content?: string; is_error?: boolean } | undefined;
  return (
    <button className={`timeline-entry tone-${presentation.tone} ${selected ? "selected" : ""}`} onClick={() => onSelect(event)}>
      <span className="timeline-icon"><Icon size={16} /></span>
      <span className="timeline-body">
        <span className="timeline-heading"><strong>{presentation.title}</strong><time>{formatTime(event.timestamp)}</time></span>
        {content && <span className="timeline-preview">{content}</span>}
        {result?.content && <span className={`timeline-preview ${result.is_error ? "error-text" : ""}`}>{result.content}</span>}
      </span>
    </button>
  );
}

function ToolEventGroup({ events, selectedEventId, onSelect }: { events: ConsoleEvent[]; selectedEventId: number | null; onSelect: (event: ConsoleEvent) => void }) {
  const modelEvent = events[0];
  const toolCalls = modelEvent.data.tool_calls as Array<{ name?: string }>;
  const resultEvents = events.filter((event) => event.event_type === "tool_result");
  const hasError = resultEvents.some((event) => (event.data.result as { is_error?: boolean } | undefined)?.is_error);
  const approvalCount = events.filter((event) => event.event_type === "approval_required").length;
  const resolvedCount = events.filter((event) => event.event_type === "approval_resolved").length;
  const status = approvalCount > resolvedCount ? "等待审批" : hasError ? "包含错误" : resultEvents.length === toolCalls.length ? "已完成" : `完成 ${resultEvents.length}/${toolCalls.length}`;
  return (
    <details className="tool-event-group">
      <summary className="tool-group-summary">
        <span className="timeline-icon"><Wrench size={16} /></span>
        <span className="timeline-body">
          <span className="timeline-heading"><strong>第 {Number(modelEvent.data.step)} 步 · {toolCalls.length} 个工具调用</strong><time>{formatTime(modelEvent.timestamp)}</time></span>
          <span className={`tool-group-status ${hasError ? "error-text" : ""}`}>{status}<ChevronRight className="tool-group-chevron" size={14} /></span>
        </span>
      </summary>
      <div className="tool-group-events">{events.map((event) => <TimelineEvent key={event.id} event={event} selected={selectedEventId === event.id} onSelect={onSelect} />)}</div>
    </details>
  );
}

export function Timeline({ events, running, selectedEventId, onSelect }: { events: ConsoleEvent[]; running: boolean; selectedEventId: number | null; onSelect: (event: ConsoleEvent) => void }) {
  const timelineItems = groupTimelineEvents(events);
  const liveOutput = pendingModelOutput(events);
  if (!timelineItems.length && !liveOutput) return <div className="empty-timeline"><Clock3 size={20} />等待第一个运行事件</div>;
  return (
    <div className="timeline">
      {timelineItems.map((item) => item.kind === "event"
        ? <TimelineEvent key={item.event.id} event={item.event} selected={selectedEventId === item.event.id} onSelect={onSelect} />
        : <ToolEventGroup key={`tool-group-${item.events[0].id}`} events={item.events} selectedEventId={selectedEventId} onSelect={onSelect} />)}
      {liveOutput && (
        <div className={`timeline-entry streaming-entry tone-model ${running ? "active" : ""}`} aria-live="polite">
          <span className="timeline-icon"><Bot size={16} /></span>
          <span className="timeline-body">
            <span className="timeline-heading"><strong>{running ? `模型正在生成 · 第 ${liveOutput.step} 步` : `模型输出中断 · 第 ${liveOutput.step} 步`}</strong><time>{formatTime(liveOutput.timestamp)}</time></span>
            <span className="streaming-output">{liveOutput.content}{running && <span className="streaming-cursor" />}</span>
          </span>
        </div>
      )}
    </div>
  );
}
