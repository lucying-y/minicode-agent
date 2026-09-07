# MiniCode Agent 校招投递准备

这份文档用于校招投递、项目介绍和面试准备。所有内容以当前仓库已经实现并通过测试的功能为准。教育经历、个人信息和真实项目时间需要替换为自己的事实，不要直接使用占位符提交简历。

## 1. 项目定位

MiniCode Agent 是一个参考 DeepSeek Harness 设计思想、自研实现的轻量级 Coding Agent Runtime。它不是简单的模型 API Demo，而是把模型、工具、权限、上下文、会话、持久化和前端观察组织成一个可组合运行时。

一句话介绍：

> 我独立实现了一个面向代码仓库任务的 Coding Agent Runtime，支持 OpenAI-compatible 模型、结构化工具调用、审批策略、流式输出、CLI/Web 双入口、事件回放和断点恢复。

## 2. 简历版本

### 2.1 一页简历短版

**MiniCode Agent：轻量级 Coding Agent Runtime** ｜个人项目｜Python / FastAPI / React / SQLite / SSE

- 独立设计并实现有界的模型-工具循环，支持最大步数、Token 总量、上下文预算、流式输出、取消和 Checkpoint 恢复。
- 参考 DeepSeek Harness 的 Capability Seam 思想，设计 `AgentHarness` 组合层和 `minimal`、`standard`、`review` Preset，解耦 Model Provider、Tool Registry、Permission Policy、Context、Session 和 Persistence。
- 使用 Pydantic/JSON Schema 实现 `read_file`、`list_files`、`search_text`、`edit_file`、`run_shell`，支持 `ask`、`auto`、`read_only` 审批模式、工作区边界和高风险命令拒绝。
- 基于 SQLite/JSONL 实现跨 CLI/Web 的 Session Event Log、Replay 和审计轨迹；Web Console 使用 React、FastAPI、SSE 展示模型增量、工具调用、审批、变更和测试结果。
- 兼容 macOS、Linux 和原生 Windows PowerShell；后端 94 个测试通过、前端 6 个测试通过，Ruff、TypeScript、Vitest、Vite 构建和 npm audit 均通过。

### 2.2 技术面试详细版

- Runtime：通过 `AgentHarness` 统一组装 Provider、Tools、Policy、Context、Trace 和 Checkpoint，`AgentRuntime` 只负责循环、状态和停止条件。
- Tool Calling：模型返回结构化 `ToolCall`，Registry 完成 Schema 校验、权限授权、工具执行和 `ToolResult` 返回；同一响应可以包含多个工具调用。
- Harness：使用 Preset 控制模型可见工具集合；使用 `ToolHook`/`AuditHook` 扩展工具生命周期，并记录 `tool_requested` 和 `tool_result`。
- Observability：Run Store 采用追加式事件记录，`SessionReplay` 从事件重建消息、状态、步数、Token 和最终输出；CLI `/replay` 与 Web Replay API 共用同一事实源。
- Reliability：Fake Provider 用于离线确定性测试；Checkpoint 只在完整模型/工具边界保存，避免恢复时重复已完成的半轮操作。
- Platform：Shell Backend 显式区分 POSIX 和 PowerShell，处理 UTF-8、中文和带空格路径、超时以及 Windows 子进程终止。

## 3. 自我介绍话术

### 30 秒

我主要做 Python 后端和 Agent Runtime。我的代表项目是 MiniCode Agent，一个可以操作代码仓库的轻量 Coding Agent。我自己实现了模型和工具循环、OpenAI-compatible 模型适配、结构化文件和 Shell 工具、审批模式、SQLite 事件时间线、Replay、Checkpoint，以及 React Web Console。这个项目重点不是调用模型，而是把 Agent 的权限、上下文、可观测性和恢复机制做完整，并且兼容 Windows PowerShell。

### 2 分钟

项目的核心问题是：模型只能提出工具调用，真正的执行必须可控、可观察、可恢复。我把系统分成几层：Provider 负责模型协议，Tool Registry 负责工具 Schema 和执行，Permission Policy 负责审批，Context Manager 负责预算，AgentRuntime 负责有界循环，Persistence 负责 Trace、Event Log 和 Checkpoint。

为了体现 Harness 思想，我新增了 AgentHarness 作为能力组合边界，用 Preset 选择不同工具集合。执行过程中，Runtime 会把模型响应、工具请求、审批、工具结果和终态写入 Session Event Log。Web Console 和 CLI 都从工作区的 SQLite 时间线读取数据，Replay 可以不依赖 Checkpoint 重建一次运行的状态。

我还处理了真实工程问题，例如 SSE 流式输出、工具结果过长、路径逃逸、危险命令、中文终端乱码、Windows PowerShell 和任务取消。最后使用 Fake Provider、HTTP Mock、后端单测、Web API 测试和前端测试验证关键路径。

## 4. 高频面试问题与回答

### Q1：为什么自己实现 Agent Loop，不直接使用 LangGraph？

当前项目的目标是理解和展示 Runtime 机制，而不是快速拼装业务 Agent。自己实现循环后，步数限制、Token 限制、工具调用协议、Checkpoint 边界和错误状态都可以被直接测试。生产项目中可以使用成熟框架，但仍需要理解框架背后的状态机和副作用边界。

### Q2：一次 Agent 运行的流程是什么？

```text
用户任务
  -> system/user messages
  -> ContextManager 选择上下文
  -> ModelProvider 请求模型
  -> ModelResponse
  -> 没有工具调用：完成
  -> 有工具调用：Schema 校验与权限审批
  -> ToolRegistry 执行
  -> ToolResult 追加到消息
  -> 进入下一步，直到完成或触发限制
```

### Q3：AgentHarness 和 AgentRuntime 的区别？

`AgentHarness` 负责依赖组合，决定本次运行使用哪个 Provider、工具集、策略、上下文和持久化实现；`AgentRuntime` 负责执行模型-工具循环。这样替换 Fake Provider、Preset 或存储实现时，不需要重写循环。

### Q4：三个 Preset 有什么区别？

- `minimal`：只有读文件、列文件、搜索，且上下文最多 8,000 Token。
- `standard`：完整的读写文件和 Shell，是默认开发模式。
- `review`：只读文件工具加 Shell，适合审查和测试，不提供 `edit_file`。

Preset 决定工具集合；`ask`、`auto`、`read_only` 决定权限策略，两者是不同层次。

### Q5：如何防止 `../secret.txt` 逃逸工作区？

所有文件工具都通过 Workspace 解析路径，转成绝对路径后检查是否仍处于工作区内，并额外阻止敏感路径。这个保护只覆盖文件工具。Shell 进程仍拥有当前用户权限，所以项目明确说明这不是操作系统沙箱；不可信任务应使用 Docker 或虚拟机。

### Q6：为什么上下文裁剪要保留完整 Assistant/Tool 块？

工具结果必须对应前一个 assistant 的 `tool_call_id`。如果只保留 tool 消息，模型会收到不完整的协议历史，可能无法继续调用或误判状态。因此 ContextManager 按完整执行块裁剪，并始终保留 system prompt 和当前任务。

### Q7：Checkpoint 为什么不在每个工具后都保存？

一个模型响应可能包含多个工具调用。当前策略在这一轮全部工具完成后保存一致边界，避免恢复时只完成一半却把消息历史当成完整状态。代价是进程在工具副作用发生后、Checkpoint 保存前崩溃时仍可能需要人工检查，这也是当前明确记录的限制。

### Q8：Event Log 和 Checkpoint 有什么区别？

Event Log 是追加式事实记录，用于时间线、审计和 Replay；Checkpoint 是最新一致状态，用于继续执行。Replay 不会重新执行工具，Resume 才会从 Checkpoint 继续运行。

### Q9：为什么要有 Fake Provider？

真实模型响应不稳定、成本高且难以覆盖错误路径。Fake Provider 可以预置模型响应和工具调用，确定性测试步数限制、工具错误、流式分片、取消和恢复。真实 Provider 仍通过独立 HTTP Mock 和可选端到端测试验证。

### Q10：流式输出怎样处理工具调用？

Provider 逐个解析 SSE chunk，拼接文本 delta；工具调用的 ID、名称和 JSON 参数按 index 累积，直到流结束后组装成完整 `ToolCall`。Runtime 只在得到完整 `ModelResponse` 后执行工具，避免执行半截 JSON。

### Q11：Web 和 CLI 是怎样互通的？

两者不共享执行控制，但共享工作区下的 `.minicode/runs.db`。CLI 和 Web 都把运行摘要和事件写入同一个 SQLite Run Store，Web 可以观察 CLI 任务；CLI 任务在 Web 中只读，审批、恢复和取消仍由原终端负责。

### Q12：审批模式能否等同于“完全访问”？

不能。`auto` 只是自动批准应用层允许的写入和执行操作，仍受工作区、敏感路径和高风险命令规则限制。它不是操作系统权限，也不是沙箱。真实不可信任务不能只依赖这个模式。

### Q13：为什么任务成功不能只看模型最终回答？

模型说“完成”不代表代码真的通过测试。因此评测使用独立校验命令检查文件或测试结果，报告以校验退出码为准。这也能避免模型通过语言掩盖工具失败。

### Q14：如果继续迭代，你会做什么？

优先做 Provider Profiles、上下文压缩和更完整的 Harness Inspector；再考虑 Subagent、PTC、多模态和 Docker Execution Backend。沙箱是安全边界增强，不应在没有稳定执行接口前直接堆进 Runtime。

## 5. 演示流程

### 离线演示

```bash
uv sync --all-groups
uv run minicode demo --workspace .
```

然后启动 Web：

```bash
cd web
npm ci
npm run build
cd ..
uv run minicode web --demo --workspace . --port 8000
```

浏览器打开 `http://127.0.0.1:8000`，展示运行时间线、工具折叠、审批和事件详情。

### CLI 演示

```bash
uv run minicode chat --workspace . --preset standard
```

推荐顺序：输入一个只读检查任务；输入 `/status`；输入 `/history`；输入 `/replay`；最后输入 `/exit`。

### 真实模型演示

确认当前目录 `.env` 已配置 `MINICODE_API_KEY`、`MINICODE_BASE_URL` 和 `MINICODE_MODEL` 后运行：

```bash
uv run minicode run "检查项目结构并运行相关测试" --workspace . --preset review
```

不要在面试演示中暴露 API Key；不要使用 `--yes` 操作不可信仓库。

## 6. 面试前检查清单

- 能解释 ModelProvider、ToolRegistry、PermissionPolicy、ContextManager、Checkpoint 和 Event Log 的职责。
- 能现场说明 `minimal`、`standard`、`review` 和三种审批模式的差异。
- 能运行离线 Demo，不依赖网络或真实 API Key。
- 能展示一次工具调用如何变成 `tool_requested`、审批、`tool_result` 和 `run_finished` 事件。
- 能解释为什么应用层路径检查不是沙箱，以及 Docker 会改变什么威胁模型。
- 能说清楚当前限制：OpenAI-compatible 协议、字符估算 Token、无 MCP/子 Agent/容器沙箱。
- 简历中的测试数量、评测数据和项目时间都与当前仓库和实际经历一致。

## 7. 不要这样写

- 不要写“基于 DeepSeek Harness 开发”；准确说法是“参考 DeepSeek Harness 的设计思想”。
- 不要写“实现了完整沙箱”或“可以安全执行任意代码”；当前没有容器沙箱。
- 不要写“支持所有模型协议”；当前是 OpenAI-compatible Chat Completions。
- 不要把自建 3 题任务集写成 SWE-bench 或公开 benchmark 成绩。
- 不要把未来规划中的 Subagent、MCP、PTC 写成已经完成。

## 8. 可直接背诵的项目结尾

这个项目让我重点理解了 Agent 的工程难点：模型本身只是决策器，真正复杂的是工具副作用、权限边界、上下文一致性、运行可观测性和失败恢复。后续如果进入团队，我希望继续在 Agent Runtime、模型工具调用和全栈调试体验方向深入。
