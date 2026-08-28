"""Tool discovery, validation, authorization, and execution."""

from collections.abc import Iterable
from time import perf_counter
from typing import Any

from pydantic import ValidationError

from minicode_agent.runtime.types import ToolCall, ToolResult, ToolSchema
from minicode_agent.security import PermissionDenied, PermissionPolicy, Workspace
from minicode_agent.tools.base import Tool
from minicode_agent.tools.hooks import ToolHook


class ToolRegistry:
    """Runtime-facing executor for a set of named tools."""

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
        """Register a hook applied to subsequent tool calls."""
        self._hooks.append(hook)

    def register(self, tool: Tool[Any]) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def schemas(self) -> list[ToolSchema]:
        return [
            ToolSchema(
                name=tool.name,
                description=tool.description,
                parameters=tool.input_model.model_json_schema(),
            )
            for tool in self._tools.values()
        ]

    async def execute(self, call: ToolCall) -> ToolResult:
        started = perf_counter()
        execution_started: float | None = None
        tool = self._tools.get(call.name)
        if tool is None:
            return ToolResult(content=f"unknown tool: {call.name}", is_error=True)

        try:
            for hook in self._hooks:
                await hook.before_execute(call, tool.permission)
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
