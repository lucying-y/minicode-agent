"""OpenAI-compatible Chat Completions Provider。

这个适配器有意只支持通用的 Chat Completions 子集，不声称兼容所有厂商扩展。它负责在
Provider 无关的 Runtime 模型与 JSON/SSE 载荷之间转换并校验响应结构，循环、权限和持久化
决策仍由其他 bundle 负责。
"""

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from minicode_agent.runtime.types import (
    Message,
    ModelResponse,
    ModelStreamChunk,
    TokenUsage,
    ToolCall,
    ToolSchema,
)


class ModelProviderError(RuntimeError):
    """Raised when a provider returns an unusable response."""


class OpenAICompatibleProvider:
    """调用 OpenAI-compatible `/chat/completions` 端点。

    测试可以注入 HTTP 客户端。由本类创建客户端时，其生命周期归 `aclose()` 管理；注入的
    客户端仍由调用方管理。
    """

    supports_streaming = True

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout_seconds: float = 120.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(timeout=timeout_seconds)

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolSchema],
    ) -> ModelResponse:
        """发送一次非流式请求并校验响应结构。"""
        try:
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=self._request_payload(messages, tools),
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ModelProviderError(f"model request failed: {exc}") from exc

        return self._parse_response(body)

    async def stream_complete(
        self,
        messages: list[Message],
        tools: list[ToolSchema],
    ) -> AsyncIterator[ModelStreamChunk]:
        """解析 OpenAI-compatible SSE 分片并组装最终响应。

        文本增量到达后立即向上游产出。工具调用按 Provider 提供的 index 累积，因为 SSE 流
        可能把 ID、函数名和 JSON 参数拆分到不同分片。只有 `_assemble_tool_calls()` 校验完
        整个 JSON 对象后，工具调用才允许进入执行阶段。
        """
        payload = self._request_payload(messages, tools)
        payload["stream"] = True
        payload["stream_options"] = {"include_usage": True}
        content_parts: list[str] = []
        tool_parts: dict[int, dict[str, str]] = {}
        usage = TokenUsage()
        saw_data = False

        try:
            async with self.client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line or line.startswith(":") or not line.startswith("data:"):
                        continue
                    raw_data = line.removeprefix("data:").strip()
                    if raw_data == "[DONE]":
                        break
                    try:
                        body = json.loads(raw_data)
                    except json.JSONDecodeError as exc:
                        raise ModelProviderError(
                            f"invalid streaming model response: {exc}"
                        ) from exc
                    if not isinstance(body, dict):
                        raise ModelProviderError(
                            "invalid streaming model response: chunk is not an object"
                        )
                    if body.get("error"):
                        raise ModelProviderError(f"streaming model error: {body['error']}")
                    saw_data = True
                    self._update_stream_usage(usage, body.get("usage"))
                    choices = body.get("choices") or []
                    if not choices:
                        continue
                    choice = choices[0]
                    if not isinstance(choice, dict):
                        raise ModelProviderError(
                            "invalid streaming model response: choice is not an object"
                        )
                    delta = choice.get("delta") or {}
                    if not isinstance(delta, dict):
                        raise ModelProviderError(
                            "invalid streaming model response: delta is not an object"
                        )

                    content = delta.get("content")
                    if content is not None:
                        if not isinstance(content, str):
                            raise ModelProviderError(
                                "invalid streaming model response: content delta is not text"
                            )
                        if content:
                            content_parts.append(content)
                            yield ModelStreamChunk(delta=content)
                    self._update_stream_tool_calls(tool_parts, delta.get("tool_calls"))
        except httpx.HTTPError as exc:
            raise ModelProviderError(f"model request failed: {exc}") from exc

        if not saw_data:
            raise ModelProviderError("invalid streaming model response: no data chunks")
        yield ModelStreamChunk(
            response=ModelResponse(
                content="".join(content_parts),
                tool_calls=self._assemble_tool_calls(tool_parts),
                usage=usage,
            )
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    def _request_payload(
        self,
        messages: list[Message],
        tools: list[ToolSchema],
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [self._message_payload(message) for message in messages],
        }
        if tools:
            payload["tools"] = [self._tool_payload(tool) for tool in tools]
            payload["tool_choice"] = "auto"
        return payload

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    @staticmethod
    def _update_stream_usage(usage: TokenUsage, raw_usage: Any) -> None:
        """当厂商返回用量信息时，从 Provider 分片复制 Token 计数。"""
        if raw_usage is None:
            return
        if not isinstance(raw_usage, dict):
            raise ModelProviderError("invalid streaming model response: usage is not an object")
        usage.input_tokens = int(raw_usage.get("prompt_tokens") or 0)
        usage.output_tokens = int(raw_usage.get("completion_tokens") or 0)

    @staticmethod
    def _update_stream_tool_calls(
        tool_parts: dict[int, dict[str, str]],
        raw_calls: Any,
    ) -> None:
        """以分片 index 为键合并被拆开的工具调用元数据。"""
        if raw_calls is None:
            return
        if not isinstance(raw_calls, list):
            raise ModelProviderError("invalid streaming model response: tool calls are not a list")
        for raw_call in raw_calls:
            if not isinstance(raw_call, dict):
                raise ModelProviderError(
                    "invalid streaming model response: tool call is not an object"
                )
            try:
                index = int(raw_call["index"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ModelProviderError(
                    "invalid streaming model response: tool call index is missing"
                ) from exc
            part = tool_parts.setdefault(index, {"id": "", "name": "", "arguments": ""})
            call_id = raw_call.get("id")
            if call_id is not None:
                part["id"] += str(call_id)
            function = raw_call.get("function") or {}
            if not isinstance(function, dict):
                raise ModelProviderError(
                    "invalid streaming model response: tool function is not an object"
                )
            name = function.get("name")
            arguments = function.get("arguments")
            if name is not None:
                part["name"] += str(name)
            if arguments is not None:
                part["arguments"] += str(arguments)

    @staticmethod
    def _assemble_tool_calls(tool_parts: dict[int, dict[str, str]]) -> list[ToolCall]:
        """校验累积的调用片段，并转换为 `ToolCall` 对象。"""
        calls: list[ToolCall] = []
        for index in sorted(tool_parts):
            part = tool_parts[index]
            if not part["id"] or not part["name"]:
                raise ModelProviderError(
                    "invalid streaming model response: incomplete tool call metadata"
                )
            try:
                arguments = json.loads(part["arguments"] or "{}")
            except json.JSONDecodeError as exc:
                raise ModelProviderError(
                    f"invalid streaming model response: invalid tool arguments: {exc}"
                ) from exc
            if not isinstance(arguments, dict):
                raise ModelProviderError(
                    "invalid streaming model response: tool arguments are not an object"
                )
            calls.append(ToolCall(id=part["id"], name=part["name"], arguments=arguments))
        return calls

    @staticmethod
    def _message_payload(message: Message) -> dict[str, Any]:
        """把一条 Runtime 消息序列化为 Chat Completions 消息 JSON。"""
        payload: dict[str, Any] = {"role": message.role, "content": message.content}
        if message.name:
            payload["name"] = message.name
        if message.tool_call_id:
            payload["tool_call_id"] = message.tool_call_id
        if message.tool_calls:
            payload["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(call.arguments, ensure_ascii=False),
                    },
                }
                for call in message.tool_calls
            ]
        return payload

    @staticmethod
    def _tool_payload(tool: ToolSchema) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }

    @staticmethod
    def _parse_response(body: dict[str, Any]) -> ModelResponse:
        """解析非流式响应，并拒绝结构不合法的工具参数。"""
        try:
            message = body["choices"][0]["message"]
            calls = []
            for raw_call in message.get("tool_calls") or []:
                function = raw_call["function"]
                arguments = function.get("arguments", "{}")
                if isinstance(arguments, str):
                    arguments = json.loads(arguments)
                if not isinstance(arguments, dict):
                    raise TypeError("tool arguments must decode to an object")
                calls.append(
                    ToolCall(
                        id=raw_call["id"],
                        name=function["name"],
                        arguments=arguments,
                    )
                )
            raw_usage = body.get("usage") or {}
            usage = TokenUsage(
                input_tokens=raw_usage.get("prompt_tokens", 0),
                output_tokens=raw_usage.get("completion_tokens", 0),
            )
            return ModelResponse(
                content=message.get("content") or "",
                tool_calls=calls,
                usage=usage,
            )
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ModelProviderError(f"invalid model response: {exc}") from exc
