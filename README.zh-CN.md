# MiniCode Agent

[English](README.md) | [简体中文](README.zh-CN.md)

MiniCode Agent 是一个面向代码仓库任务的轻量级、可审查 Coding Agent Runtime。本项目独立实现，
重点关注 Agent 背后的工程机制，包括执行流程、结构化工具、上下文限制、权限控制、模型适配和
运行轨迹。

项目在架构设计上参考了
[mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent)、
[teenycode](https://github.com/yangshun/teenycode) 和
[learn-claude-code](https://github.com/shareAI-lab/learn-claude-code)，但不依赖或复制现有 Agent
框架。

第一次接触 Agent 的读者，建议先阅读
[《代码设计与技术细节》](docs/code-design.zh-CN.md)。该文档从基础概念开始，详细解释一次任务的
执行流程、模型与工具协议、上下文、权限、Trace、Checkpoint、评测以及当前安全边界。

## 当前能力

- 实现有界的模型-工具执行循环，支持最大步数、Token 总量和上下文预算限制。
- 使用与模型供应商无关的消息结构，并提供兼容 OpenAI Chat Completions 的适配器。
- 使用 Pydantic 定义工具参数，并以 JSON Schema 形式提供给模型。
- 提供限定在工作区内的 `read_file`、`list_files`、`search_text`、`edit_file` 和
  `run_shell` 工具。
- 支持读、写、执行三级权限，并在状态变更操作前请求人工确认。
- 使用唯一文本精确替换，使文件修改过程更可预测、便于审查。
- 使用只追加的 JSONL 轨迹记录模型响应、工具结果、Token 用量、耗时和最终状态。
- 使用 SQLite 保存一致执行边界上的消息、累计用量和轨迹序号，支持断点恢复。
- 提供可重复运行的仓库任务评测，通过确定性校验命令判断结果并生成 JSON 报告。
- 提供确定性的 Fake Provider，用于离线测试和演示。

## 快速开始

项目需要 Python 3.12+ 和 [uv](https://docs.astral.sh/uv/)。

```bash
uv sync --all-groups
uv run minicode demo --workspace .
```

演示命令不会调用外部模型。它会执行一次预设工具调用，并将运行轨迹写入
`.minicode/traces.jsonl`。

## 配置模型

复制环境变量示例文件，并填写兼容 OpenAI 接口的服务信息：

```bash
cp .env.example .env
```

```dotenv
MINICODE_API_KEY=your-api-key
MINICODE_BASE_URL=https://your-provider.example/v1
MINICODE_MODEL=your-model-name
```

API Key 从本地 `.env` 文件加载。该文件已被 Git 忽略，不需要写入源代码或命令行参数。

运行一个代码仓库任务：

```bash
uv run minicode run "检查项目并修复失败的测试" --workspace /path/to/repo
```

文件写入和 Shell 命令默认需要人工确认。对于可信任务，可以使用 `--yes` 跳过交互确认，
但匹配内置高风险拒绝规则的命令仍会被阻止。

每次运行都会输出一个 `run_id`。如果任务因步数限制、Token 限制、工具错误或模型服务错误
而停止，可在调整限制或修复外部问题后，从最后一个一致的模型/工具边界继续执行：

```bash
uv run minicode resume RUN_ID --workspace /path/to/repo --max-steps 24
```

Checkpoint 保存在 `.minicode/checkpoints.db`。已经完成的运行记录不可修改，也不能再次恢复。

## 评测

配置模型后，可运行项目内置的 3 题任务集：

```bash
uv run minicode eval --tasks evals/tasks.json
```

每次评测都会创建独立的 `.minicode/evals/<timestamp>-<id>/` 目录，其中包含：

- 每个任务对应的隔离工作区；
- 每次运行的完整 JSONL 轨迹和 SQLite Checkpoint；
- `report.json`，记录通过状态、Runtime 状态、执行步数、输入/输出 Token 和耗时。

任务是否成功由独立校验命令决定，而不是依据模型的最终回复。只要存在未通过的任务，评测命令
就会以状态码 1 退出。评测文件可以包含可执行命令，因此只能运行可信的任务集，建议在一次性
容器中执行外部评测任务。

### 已验证基线

2026-08-03，`gpt-5.6-sol` 通过真实模型调用链路完成了项目内置的全部 3 个仓库任务：

| 结果 | 平均步数 | 总 Token | 总耗时 |
| --- | ---: | ---: | ---: |
| 3/3 通过 | 5 | 18,415 | 106.14 秒 |

3 次运行均达到 `completed` 状态，独立校验命令的退出码均为 0。汇总数据和每题明细保存在
[`benchmarks/gpt-5.6-sol-baseline-20260803.json`](benchmarks/gpt-5.6-sol-baseline-20260803.json)。
这是一组自建的小型回归任务，不代表项目在 SWE-bench 或其他公开基准上的表现。

## 执行流程

```text
任务
  -> 上下文管理器
  -> 模型适配器
  -> 零个或多个结构化工具调用
  -> Schema 参数校验
  -> 权限策略检查
  -> 工作区工具执行
  -> 将工具结果追加到消息历史
  -> 进入下一轮模型调用或终止状态
```

Runtime 会在内存中保留完整执行轨迹。每次请求模型前，上下文管理器都会保留系统提示、原始
任务，以及预算范围内最新且完整的 Assistant/Tool 消息块，避免工具结果失去对应的原始调用。

## 安全边界

路径检查、高风险命令拒绝和人工确认均属于应用层控制，并非操作系统级沙箱，无法保证任意模型
生成的 Shell 命令绝对安全。处理不可信代码仓库或任务时，应使用一次性容器或虚拟机。

## 开发与测试

```bash
uv run ruff check .
uv run pytest --cov
```

测试使用临时工作区、模拟 HTTP 响应和确定性模型，覆盖 Agent Loop、运行限制、上下文选择、
路径逃逸防护、人工确认、文件工具、命令失败与超时、Checkpoint 恢复、模型协议转换、CLI
演示、仓库任务评测和 JSONL 事件顺序。

## 项目结构

```text
src/minicode_agent/
├── runtime/       # Agent Loop、状态类型、上下文预算
├── models/        # 模型协议、Fake Provider、OpenAI 兼容适配器
├── tools/         # 工具 Schema、注册中心、文件系统与 Shell 工具
├── security/      # 工作区边界与权限策略
├── persistence/   # 只追加 JSONL 轨迹与 SQLite Checkpoint
├── evaluation/    # 任务定义、隔离执行、结果校验与报告
└── cli.py         # 离线演示与真实模型命令入口
```

## 当前限制

- 模型适配器目前使用 `/chat/completions`，尚未实现流式输出。
- 上下文用量通过序列化后的字符长度估算，尚未使用模型对应的 Tokenizer。
- MCP、多 Agent 和 Web Console 暂未实现，当前优先保证单 Agent Runtime 和评测基线稳定。

## 后续计划

1. 扩充评测任务，并比较不同模型和运行参数组合。
2. 增加 SSE API 和轻量级 React 执行控制台。
3. 增加基于 Docker 的隔离执行环境。
