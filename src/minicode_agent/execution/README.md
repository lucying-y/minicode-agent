# Execution Bundle

`execution` 负责在当前平台启动受控命令。它不解析命令业务含义，而是选择正确的解释器、限制输出、处理超时和终止进程树。

## Shell 后端

- `PosixShellBackend`：macOS/Linux 使用 `bash -lc`。
- `PowerShellBackend`：Windows 使用 `powershell.exe` 或 `pwsh`，并显式设置 UTF-8 输出。
- `detect_shell()`：优先按平台和可执行文件探测，失败时抛出 `ShellUnavailableError`。

## 运行保证

`ShellBackend.run()` 返回统一的 `CommandResult`，包含输出、退出码、是否超时和是否截断。输出按 UTF-8 丢弃非法字节并限制最大字符数；取消或超时会尝试终止子进程树。PowerShell 和 POSIX 的命令语法不会互相转换，模型会从 `platform_system_prompt()` 得到当前平台提示。
