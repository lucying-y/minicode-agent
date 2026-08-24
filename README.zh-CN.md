# MiniCode Agent

[English](README.md) | [简体中文](README.zh-CN.md)

[![CI](https://github.com/lucying-y/minicode-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/lucying-y/minicode-agent/actions/workflows/ci.yml)

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
- 支持读、写、执行三级权限，以及人工审批、自动批准允许项和只读三种运行模式。
- 使用唯一文本精确替换，使文件修改过程更可预测、便于审查。
- 使用只追加的 JSONL 轨迹记录模型响应、工具结果、Token 用量、耗时和最终状态。
- 使用 SQLite 保存一致执行边界上的消息、累计用量和轨迹序号，支持断点恢复。
- 使用工作区级 SQLite Run Store，让 CLI 与 Web 跨进程共享运行摘要和时间线。
- 提供持久化交互式 CLI，在同一会话中保留多轮上下文并支持斜杠命令。
- 提供可重复运行的仓库任务评测，通过确定性校验命令判断结果并生成 JSON 报告。
- 提供确定性的 Fake Provider，用于离线测试和演示。
- 提供本地 React Web Console，通过 FastAPI、SSE、网页审批、主动取消和 Checkpoint 恢复观察与
  控制任务。
- Web 任务可在模型请求、等待审批或 Shell 执行阶段取消；CLI 使用 `Ctrl+C` 时也会保存取消状态。
- 以任务启动时的 Git 可见文件为基线，生成结构化文件变更、增删行和 Unified Diff。
- 自动识别常见测试命令，将退出码、耗时、通过/失败/跳过数量投影到 Web 测试视图。

## 快速开始

项目需要 Python 3.12+ 和 [uv](https://docs.astral.sh/uv/)。Web Console 还需要 Node.js 20.19+
（建议使用 Node.js 22 LTS）。支持 macOS、Linux，以及不依赖 WSL 的原生 Windows PowerShell。

```bash
uv sync --all-groups
uv run minicode demo --workspace .
```

演示命令不会调用外部模型。它会执行一次预设工具调用，将可读轨迹写入
`.minicode/traces.jsonl`，并将共享时间线写入 `.minicode/runs.db`。

### 原生 Windows PowerShell

Windows 10/11 可直接使用 PowerShell，不需要 WSL 或 Git Bash。程序优先检测 PowerShell 7 的
`pwsh.exe`，未安装时回退到系统自带的 Windows PowerShell 5.1 `powershell.exe`。模型会收到当前
操作系统、PowerShell 版本和工作区信息，`run_shell`、Web Demo 和评测校验命令共用同一个
PowerShell 执行后端，不会隐式转交给 `cmd.exe`。

在 PowerShell 中首次安装和构建：

```powershell
git clone https://github.com/lucying-y/minicode-agent.git
Set-Location minicode-agent
uv sync --all-groups

Set-Location web
npm ci
npm run build
Set-Location ..

Copy-Item .env.example .env
notepad .env
```

运行交互式 CLI 或 Web Console：

```powershell
uv run minicode chat --workspace "C:\Users\damon\projects\demo"
uv run minicode web --workspace "C:\Users\damon\projects\demo" --port 8000
```

Windows 命令输出统一按 UTF-8 读取，支持带空格和中文的工作区路径。命令超时时会终止 PowerShell
及其子进程；CLI 启动信息和 Web `/api/health` 会显示实际选中的 Shell。PowerShell 命令仍以当前
Windows 用户权限运行，审批和危险命令拒绝不是操作系统沙箱，不要对不可信任务使用 `--yes`。

### Web Console

首次使用需要安装并构建前端：

```bash
cd web
npm ci
npm run build
cd ..
uv run minicode web --demo --workspace /path/to/repo
```

浏览器打开 <http://127.0.0.1:8000>。`--demo` 使用脚本化 Fake Provider，不消耗 API Token，
并会在执行 Shell 命令前停下来等待网页批准。使用 `.env` 中的真实模型配置时，运行：

```bash
uv run minicode web --workspace /path/to/repo
```

`--workspace` 设置页面创建任务时的默认工作区，仍可在每个新任务中单独修改。Fake Provider 和
真实模型都会把模型文本增量显示在执行时间线中。

只要 Web 与 CLI 使用相同的 `--workspace`，Web 还会显示之后从 CLI 发起的任务。CLI 任务在网页
中只读：审批和恢复仍须回到原终端完成，Web 不会接管 CLI 的执行控制。

端口不与模型模式绑定。需要同时运行演示和真实模型时，可约定演示使用 `8000`、真实模型使用
`8001`，也可以通过 `--port` 选择任意空闲端口。

界面操作、API、运行生命周期和数据保存方式见
[《Web Console 使用与设计说明》](docs/web-console.zh-CN.md)。

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

### 交互式 CLI

进入需要操作的项目目录后，可以启动一个持续会话。`minicode` 不带子命令时等价于
`minicode chat`：

```bash
uv run minicode chat --workspace /path/to/repo
```

会话中的多次输入共用同一个 `run_id`、模型消息历史、累计 Token、审批器、Checkpoint 和 Web
时间线。Chat 模式下，`--max-steps` 表示每条用户消息最多允许的模型步数，而总 Token 上限作用于
整个会话。

| 命令 | 作用 |
| --- | --- |
| `/help` | 显示命令帮助 |
| `/status` | 显示 Run ID、状态、累计步数、Token 和消息数 |
| `/history` | 显示当前会话中的用户消息 |
| `/clear` | 结束当前 Run，创建一个没有旧上下文的新 Run |
| `/exit`、`/quit` | 退出 MiniCode；直接输入 `exit` 或 `quit` 也可以 |

如果希望在任意项目目录直接输入 `minicode`，可以安装一次当前源码：

```bash
uv tool install -e .
cd /path/to/repo
minicode
```

安装后的命令读取 Shell 中的 `MINICODE_*` 环境变量，或者启动目录下的 `.env`。

运行一个代码仓库任务：

```bash
uv run minicode run "检查项目并修复失败的测试" --workspace /path/to/repo
```

文件写入和 Shell 命令默认需要人工确认。对于可信任务，可以使用 `--yes` 跳过交互确认，
但匹配内置高风险拒绝规则的命令仍会被阻止。

也可以显式选择审批模式：

```bash
uv run minicode run "只检查仓库" --workspace /path/to/repo --approval-mode read_only
uv run minicode run "修复并测试" --workspace /path/to/repo --approval-mode auto
```

`--yes` 是 `--approval-mode auto` 的兼容别名。三种模式都不能绕过工作区、敏感路径和高风险
命令限制。

每次运行都会输出一个 `run_id`。如果任务因步数限制、Token 限制、工具错误或模型服务错误
而停止，可在调整限制或修复外部问题后，从最后一个一致的模型/工具边界继续执行：

```bash
uv run minicode resume RUN_ID --workspace /path/to/repo --max-steps 24
```

Checkpoint 保存在 `.minicode/checkpoints.db`，CLI/Web 共用的运行摘要和时间线保存在
`.minicode/runs.db`。已经完成的运行记录不可修改，也不能再次恢复。

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
cd web
npm run check
npm test
npm run build
```

测试使用临时工作区、模拟 HTTP 响应和确定性模型，覆盖 Agent Loop、运行限制、上下文选择、
路径逃逸防护、人工确认、文件工具、命令失败与超时、Checkpoint 恢复、模型协议转换、CLI
演示、交互式多轮上下文、仓库任务评测和 JSONL 事件顺序。

## 项目结构

```text
src/minicode_agent/
├── runtime/       # Agent Loop、状态类型、上下文预算
├── models/        # 模型协议、Fake Provider、OpenAI 兼容适配器
├── tools/         # 工具 Schema、注册中心、文件系统与 Shell 工具
├── artifacts/     # 任务级文件变更快照与结构化测试结果
├── security/      # 工作区边界与权限策略
├── persistence/   # JSONL 轨迹、SQLite Checkpoint 与共享运行时间线
├── evaluation/    # 任务定义、隔离执行、结果校验与报告
├── web/           # FastAPI、持久化 Run Manager、SSE 与网页审批
└── cli.py         # 离线演示与真实模型命令入口
web/               # React、TypeScript 与 Vite 控制台
```

## 当前限制

- 模型适配器使用 OpenAI 兼容 `/chat/completions`，支持标准 SSE 增量输出，但不适配服务商专有协议。
- 上下文用量通过序列化后的字符长度估算，尚未使用模型对应的 Tokenizer。
- Web 只发现启动时配置的工作区，以及本次服务运行期间创建过 Web 任务的其他工作区。已有的旧
  JSONL Trace 不会自动回填到 `.minicode/runs.db`。
- Web 只能取消当前服务进程创建的任务，不能从网页中断另一个 CLI 进程；取消也不会回滚已经发生的
  文件修改或其他副作用。
- 任务变更只覆盖 Git 可见且未忽略的文件；超过 1 MB 或包含 NUL 的文件只记录二进制变化，不生成
  文本 Diff。
- 当前没有 Docker 沙箱、多用户认证、MCP 或多 Agent 编排。

## 后续计划

1. 增加基于 Docker 的隔离执行环境。
2. 扩充评测任务，并比较不同模型和运行参数组合。
3. 增加模型请求重试、Token 精确计算和 Trace 敏感信息脱敏。
