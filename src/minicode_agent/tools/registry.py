"""工具发现、校验、授权和执行。

`ToolRegistry` 是模型生成的 `ToolCall` 数据与副作用之间唯一的入口。在这里统一校验、授权、
执行和 Hook 的顺序，可以避免不同工具意外采用不同的安全或可观测性规则。
"""

from collections.abc import Iterable
from time import perf_counter
from typing import Any

from pydantic import ValidationError

from minicode_agent.runtime.types import ToolCall, ToolResult, ToolSchema
from minicode_agent.security import PermissionDenied, PermissionPolicy, Workspace
from minicode_agent.tools.base import Tool
from minicode_agent.tools.hooks import ToolHook


class ToolRegistry:
    """面向 Runtime 的命名工具执行器。

    一个 Registry 拥有一个 `Workspace` 和一套策略。工具 Schema 由已注册工具的 Pydantic
    输入模型生成，因此模型可见的契约与 Runtime 校验契约不会各自漂移。
    """

    def __init__(
        self,
        workspace: Workspace,
        policy: PermissionPolicy | None = None,
        hooks: Iterable[ToolHook] = (),
    ) -> None:
        self.workspace = workspace
        self.policy = policy or PermissionPolicy()
        self._tools: dict[str, Tool[Any]] = {}
        self._hooks: list[ToolHook] = list(hooks)

    def add_hook(self, hook: ToolHook) -> None:
        """注册一个将应用于后续工具调用的 Hook。"""
        self._hooks.append(hook)

    def register(self, tool: Tool[Any]) -> None:
        """向模型可见的 Registry 中添加一个名称唯一的工具。"""
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def schemas(self) -> list[ToolSchema]:
        """按注册顺序返回本次模型请求需要的 JSON Schema。"""
        return [
            ToolSchema(
                name=tool.name,
                description=tool.description,
                parameters=tool.input_model.model_json_schema(),
            )
            for tool in self._tools.values()
        ]

    async def execute(self, call: ToolCall) -> ToolResult:
        """校验、授权、执行并审计一次结构化工具调用。

        异常会转换为 `ToolResult`，由 Runtime 根据 `stop_on_tool_error` 决定继续还是停止。
        Hook 异常也会与工具实现隔离，并作为错误结果返回，而不是未留时间线记录就直接逸出。
        """
        started = perf_counter()
        execution_started: float | None = None
        tool = self._tools.get(call.name)
        if tool is None:
            return ToolResult(content=f"unknown tool: {call.name}", is_error=True)

        try:
            for hook in self._hooks:
                await hook.before_execute(call, tool.permission)
            # 先校验参数再请求审批，确保审批者看到的操作符合公开 Schema。
            data = tool.input_model.model_validate(call.arguments)
            await self.policy.authorize(call, tool.permission)
            execution_started = perf_counter()
            result = await tool.run(data, self.workspace)
        except ValidationError as exc:
            result = ToolResult(content=f"invalid arguments: {exc}", is_error=True)
        except (OSError, PermissionDenied, ValueError) as exc:
            result = ToolResult(content=f"{type(exc).__name__}: {exc}", is_error=True)
        except Exception as exc:
            result = ToolResult(content=f"hook error: {type(exc).__name__}: {exc}", is_error=True)

        finished = perf_counter()
        result.metadata["duration_ms"] = round(
            (finished - (execution_started or started)) * 1000,
            3,
        )
        if execution_started is not None:
            result.metadata["authorization_ms"] = round((execution_started - started) * 1000, 3)
        result.metadata["tool"] = call.name
        for hook in self._hooks:
            try:
                result = await hook.after_execute(call, tool.permission, result)
            except Exception as exc:
                result = ToolResult(
                    content=f"hook error: {type(exc).__name__}: {exc}",
                    is_error=True,
                    metadata={"tool": call.name},
                )
                break
        result.metadata.setdefault("duration_ms", round((finished - started) * 1000, 3))
        result.metadata.setdefault("tool", call.name)
        return result
