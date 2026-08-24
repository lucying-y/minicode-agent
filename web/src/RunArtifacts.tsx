import { CheckCircle2, FileCode2, FlaskConical, XCircle } from "lucide-react";
import type { ConsoleEvent, TestResult, WorkspaceChanges } from "./types";

function changeSegments(events: ConsoleEvent[]): WorkspaceChanges[] {
  return events
    .filter((event) => event.event_type === "workspace_changes")
    .map((event) => event.data as unknown as WorkspaceChanges);
}

function testResults(events: ConsoleEvent[]): TestResult[] {
  return events
    .filter((event) => event.event_type === "test_result")
    .map((event) => event.data as unknown as TestResult);
}

export function artifactCounts(events: ConsoleEvent[]) {
  return {
    changes: changeSegments(events).reduce((count, segment) => count + segment.files.length, 0),
    tests: testResults(events).length,
  };
}

export function ChangesView({ events }: { events: ConsoleEvent[] }) {
  const segments = changeSegments(events);
  const unavailable = segments.find((segment) => !segment.available);
  const files = segments.flatMap((segment) => segment.files);
  const additions = segments.reduce((total, segment) => total + segment.additions, 0);
  const deletions = segments.reduce((total, segment) => total + segment.deletions, 0);
  if (!segments.length) return <div className="artifact-empty"><FileCode2 size={20} />任务结束后将显示文件变化</div>;
  if (!files.length) return <div className="artifact-empty"><FileCode2 size={20} />{unavailable?.reason || "本次运行没有修改 Git 可见文件"}</div>;
  return (
    <div className="artifact-view">
      <div className="artifact-summary"><strong>{files.length} 个文件</strong><span className="diff-add">+{additions}</span><span className="diff-delete">-{deletions}</span></div>
      {files.map((file, index) => (
        <details className="artifact-item" key={`${index}-${file.path}`}>
          <summary><span className={`change-status change-${file.status}`}>{file.status}</span><strong>{file.path}</strong><span className="diff-add">+{file.additions ?? "-"}</span><span className="diff-delete">-{file.deletions ?? "-"}</span></summary>
          {file.binary ? <div className="artifact-note">二进制文件或文件过大，未生成文本 Diff</div> : <pre className="diff-output">{file.patch || "文件内容发生变化"}</pre>}
        </details>
      ))}
    </div>
  );
}

export function TestsView({ events }: { events: ConsoleEvent[] }) {
  const results = testResults(events);
  if (!results.length) return <div className="artifact-empty"><FlaskConical size={20} />尚未识别到测试命令</div>;
  return (
    <div className="artifact-view">
      {results.map((result, index) => (
        <details className="artifact-item test-artifact" key={`${index}-${result.command}`}>
          <summary>
            {result.status === "passed" ? <CheckCircle2 className="test-pass" size={17} /> : <XCircle className="test-fail" size={17} />}
            <strong>{result.command}</strong><span>{result.duration_ms == null ? "--" : `${(result.duration_ms / 1000).toFixed(2)}s`}</span>
          </summary>
          <div className="test-counts"><span>{result.passed ?? 0} 通过</span><span>{result.failed ?? 0} 失败</span><span>{result.skipped ?? 0} 跳过</span><span>退出码 {result.exit_code ?? "--"}</span></div>
          <pre className="test-output">{result.output_excerpt || "命令没有输出"}</pre>
        </details>
      ))}
    </div>
  );
}
