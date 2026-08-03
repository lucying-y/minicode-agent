"""OpenAI-compatible chat-completions provider."""

import json
from typing import Any

import httpx

from minicode_agent.runtime.types import (
    Message,
    ModelResponse,
    TokenUsage,
    ToolCall,
    ToolSchema,
)


class ModelProviderError(RuntimeError):
    """Raised when a provider returns an unusable response."""


class OpenAICompatibleProvider:
    """Call an OpenAI-compatible `/chat/completions` endpoint."""

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
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [self._message_payload(message) for message in messages],
        }
        if tools:
            payload["tools"] = [self._tool_payload(tool) for tool in tools]
            payload["tool_choice"] = "auto"

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ModelProviderError(f"model request failed: {exc}") from exc

        return self._parse_response(body)

    async def aclose(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    @staticmethod
    def _message_payload(message: Message) -> dict[str, Any]:
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

