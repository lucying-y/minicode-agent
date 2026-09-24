# Persistence Bundle

`persistence` 保存 Agent 的运行事实和可恢复状态，使 CLI 与 Web 能共享同一工作区时间线。

## 三类数据

- Trace：`JsonlTraceSink` 追加完整 Runtime 事件，适合调试和离线分析。
- Run Store：`SqliteRunStore` 保存运行摘要和有序事件，Web/CLI 通过 `.minicode/runs.db` 共享。
- Checkpoint：`SqliteCheckpointStore` 保存每个 run 的最新一致消息、步数、Token 和终态信息。

`SessionReplay` 只根据事件重建展示状态，不重复执行工具；`AgentRuntime.resume()` 才会从 Checkpoint 继续执行。`PersistentRunRecorder` 负责同时写 Trace、Run Store，并把高频模型文本 delta 批量写入，避免每个字符都产生一次 SQLite 事务。

## 一致性原则

Run Store 追加事件与更新摘要在同一个 SQLite 事务中完成。Checkpoint 在一轮全部工具完成后保存，避免恢复时只恢复半轮工具调用。JSONL Trace 是诊断日志，不作为恢复的唯一事实源。
