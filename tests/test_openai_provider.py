import json

import httpx
import pytest

from minicode_agent.models import ModelProviderError, OpenAICompatibleProvider
from minicode_agent.runtime import Message, ToolSchema


async def test_provider_translates_tools_and_parses_tool_calls() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer secret"
        body = json.loads(request.content)
        assert body["model"] == "test-model"
        assert body["tools"][0]["function"]["name"] == "read_file"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {
                                        "name": "read_file",
                                        "arguments": '{"path":"README.md"}',
                                    },
                                }
                            ],
                        }
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 3},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider(
        api_key="secret",
        base_url="https://example.test/v1",
        model="test-model",
        client=client,
    )

    response = await provider.complete(
        [Message(role="user", content="inspect")],
        [
            ToolSchema(
                name="read_file",
                description="Read a file",
                parameters={"type": "object"},
            )
        ],
    )
    await client.aclose()

    assert response.tool_calls[0].name == "read_file"
    assert response.tool_calls[0].arguments == {"path": "README.md"}
    assert response.usage.total_tokens == 13


async def test_provider_rejects_invalid_response_shape() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"choices": []}))
    )
    provider = OpenAICompatibleProvider(
        api_key="secret",
        base_url="https://example.test/v1",
        model="test-model",
        client=client,
    )

    with pytest.raises(ModelProviderError, match="invalid model response"):
        await provider.complete([Message(role="user", content="test")], [])
    await client.aclose()

