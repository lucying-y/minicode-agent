# DeepSeek Harness 调研与 MiniCode 迭代路线

## 1. 调研结论

DeepSeek Harness 的核心价值不在于“工具数量多”，而在于把 Agent 运行时拆成可以替换和组合的能力：模型、工具、权限、上下文、会话、执行环境、存储、循环和界面都通过清晰的接口连接。

MiniCode 已经实现了其中一部分能力，但此前这些能力分散在 CLI、Web 和 Runtime 组装代码中。后续迭代的目标，是把这些能力显式组织成一个轻量 Harness，让读者能够直接看出：这是一个可组合、可观察、可恢复的 Coding Agent Runtime。

## 2. 目标架构

```text
AgentHarness
├── Model Provider       模型调用和流式响应
├── Tool Registry        工具 Schema、参数校验和执行
├── Permission Policy    读写执行权限与审批
├── Context Manager      上下文预算和裁剪
├── Session/Event Log    追加式运行事件
├── Checkpoint Store     可恢复状态
└── Execution Backend    本地 Shell，后续可扩展沙箱
```

Harness 负责“组装能力”，AgentRuntime 负责“执行循环”。这样可以在不改动循环逻辑的情况下替换模型、工具集、审批策略或持久化实现。

## 3. P0 优先事项

### P0-1：AgentHarness 组合层

新增一个轻量的 `AgentHarness`，统一持有模型、工具、配置、上下文、Trace 和 Checkpoint。CLI、Web、评测都通过这个入口构造运行时，避免每个入口重复组装依赖。

### P0-2：Preset 能力

通过配置组合不同用途的 Agent，而不是复制多套 Runtime：

| Preset | 工具和策略 | 使用场景 |
| --- | --- | --- |
| `minimal` | 只读工具，较小上下文 | 快速检查和演示 |
| `standard` | 读写文件、Shell、人工审批 | 默认开发任务 |
| `review` | 只读分析和测试执行 | Code Review 和风险检查 |

CLI 可以使用 `--preset review`，Web 创建任务时显示当前 Preset 及其能力摘要。

### P0-3：Session Event Log 和 Replay

将 Session 事件作为运行事实来源，再从事件投影出时间线、消息历史、状态和用量：

```text
Append-only Event Log
        ↓
Timeline / Message / Status / Usage Projection
        ↓
Web 观察、CLI 查询、Replay、JSON 导出
```

当前 SQLite Run Store 已经具备事件记录基础，后续需要统一事件类型、补充 `model_request`、`tool_requested` 和 `context_compacted` 等事件，并增加回放接口。

### P0-4：Tool Pipeline 和 Hooks

工具调用按照固定管线执行：

```text
before_execute → 参数校验 → 权限/审批 → 工具执行 → after_execute → 事件记录
```

Hooks 可用于审计、脱敏、耗时统计和限流，保持工具实现本身简单。

## 4. P1 优先事项

1. Provider Profiles：支持多个模型、Base URL、上下文窗口和流式能力配置。
2. Context Compaction：先裁剪过长工具输出，再通过摘要事件压缩历史。
3. Harness Inspector：在 CLI 和 Web 展示当前 Provider、Preset、工具、审批、上下文和存储配置。

## 5. P2 优先事项

1. Subagent：测试、审查和文档等可持续子会话。
2. PTC / Code Mode：在受限范围内批量调用工具。
3. 多模态输入：图片、截图和测试失败结果。
4. Docker 沙箱：在 `ExecutionBackend` 接口稳定后增加隔离执行后端。

沙箱暂时降为 P2。现阶段继续使用工作区边界、危险命令拒绝、审批模式和 PowerShell 超时；这些是应用层防护，不等同于操作系统沙箱。

## 6. 简历可用项目描述

> 参考 DeepSeek Harness 的 Capability Seam 思想，自研轻量级 Coding Agent Harness，将 Model、Tool、Policy、Context、Session 和 Checkpoint 解耦，通过 Preset 组合不同 Agent 能力，并支持 CLI/Web 双入口、流式模型调用、权限审批、事件时间线和断点恢复。

## 7. 实现原则

- 保持 Python 代码轻量、可读，优先复用现有接口。
- 先稳定能力边界，再增加复杂插件或沙箱。
- 所有运行配置写入时间线，但不记录 API Key。
- 不持久化模型隐式思维链，只记录模型可见消息、工具调用、工具结果和状态事件。
- 每个迭代点独立测试并单独提交，避免大批量混合变更。
