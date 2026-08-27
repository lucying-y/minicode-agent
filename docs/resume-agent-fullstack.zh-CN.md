# Agent 开发 / 全栈开发实习简历草稿

## 求职意向

Agent 开发实习生 / 全栈开发实习生

## 教育经历

**硕士：计算机相关专业** ｜ `20XX.09 - 20XX.06`

主修软件工程、分布式系统、数据库、机器学习等课程，关注大模型应用与 Agent Runtime 工程化。

**本科：计算机科学与技术** ｜ `20XX.09 - 20XX.06`

系统学习数据结构与算法、操作系统、计算机网络、数据库原理、软件工程和 Web 开发。

## 技术栈

- **编程语言**：Python、TypeScript/JavaScript、SQL、Shell/PowerShell
- **后端**：FastAPI、Pydantic、异步编程、HTTP/SSE、SQLite
- **前端**：React、Vite、基础 HTML/CSS、响应式页面和事件流渲染
- **Agent 工程**：模型-工具循环、OpenAI-compatible API、Function Calling、流式输出、上下文预算、权限审批、Trace、Checkpoint、事件时间线
- **工程基础**：Git、pytest、Vitest、Ruff、CI、Windows/macOS/Linux 开发环境

## 项目经历

### MiniCode Agent：轻量级 Coding Agent Runtime

**个人项目 ｜ Python / FastAPI / React / SQLite / SSE**

- 独立设计并实现有界的模型-工具执行循环，支持最大步数、Token 总量、上下文预算和结构化终态。
- 参考 DeepSeek Harness 的 Capability Seam 思想，设计可组合的 `AgentHarness`，解耦 Model Provider、Tool Registry、Permission Policy、Context、Session 和 Checkpoint。
- 使用 Pydantic 定义工具输入模型并生成 JSON Schema，实现 `read_file`、`list_files`、`search_text`、`edit_file` 和 `run_shell` 等工作区工具。
- 实现 `ask`、`auto`、`read_only` 三种审批模式，结合路径边界和高风险命令拒绝规则控制模型对仓库的修改权限。
- 基于 OpenAI-compatible Chat Completions 实现真实模型适配和 SSE 流式输出，同时提供 Fake Provider 支持离线演示与确定性测试。
- 使用 SQLite 保存跨 CLI/Web 的 Run Store 和追加式事件时间线，使用 JSONL Trace 与 SQLite Checkpoint 支持审计、恢复和多入口观察。
- 实现 React Web Console，展示模型增量、工具调用、审批请求、Git 变更、测试结果和运行状态；CLI 与 Web 共享同一工作区时间线数据。
- 兼容 macOS、Linux 和原生 Windows PowerShell，处理中文输出、带空格路径、Shell 超时和子进程终止。
- 编写后端单元测试、Provider HTTP 测试、Web API 测试和前端组件测试，并通过 Ruff、Vitest、Vite 构建和 CI 检查。

## 自我评价

- 具备计算机基础和完整项目落地能力，能够从接口设计、后端实现、前端展示到测试和文档独立推进。
- 对 Agent 的重点理解在运行时工程：工具协议、权限边界、上下文管理、可观测性、恢复机制和评测，而不是只调用模型 API。
- 重视可读性和可验证性，习惯先阅读现有代码，再用小步提交和测试结果控制变更风险。
- 能够快速学习新模型协议和 Web 技术，并将抽象设计落实为可运行、可演示的功能。
