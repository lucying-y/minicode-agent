# Tools Bundle

`tools` 是模型可以请求的结构化能力层。它负责定义输入 Schema、暴露工具描述、执行工作区操作，并统一处理权限、错误和审计 Hook。

## 默认工具

`create_default_registry()` 注册：`read_file`、`list_files`、`search_text`、`edit_file` 和 `run_shell`。Preset 可以通过 `allowed_tools` 缩小可见集合；模型看不到未注册的工具。

## 调用生命周期

`ToolRegistry.execute()` 按以下顺序处理一次 `ToolCall`：查找名称 -> 触发 before Hook -> Pydantic 参数校验 -> `PermissionPolicy.authorize()` -> 调用工具 -> 记录耗时和错误 -> 触发 after Hook。未知工具和异常会返回 `ToolResult(is_error=True)`，由 Runtime 决定是否停止。

## 扩展方式

新增工具应继承 `Tool[InputModel]`，声明稳定的 `name`、`description`、`permission` 和 `input_model`，并在 `run()` 中只做一项清晰的操作。文件路径必须通过 `Workspace.resolve()`；不要在工具里自行拼接或绕过工作区边界。
