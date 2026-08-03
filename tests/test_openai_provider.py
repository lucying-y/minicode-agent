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


async def test_provider_streams_text_and_assembles_tool_calls() -> None:
    stream_body = "\n\n".join(
        [
            'data: {"choices":[{"delta":{"content":"Hello "}}]}',
            (
                'data: {"choices":[{"delta":{"content":"world",'
                '"tool_calls":[{"index":0,"id":"call-1","function":'
                '{"name":"read_","arguments":"{\\"path\\":"}}]}}]}'
            ),
            (
                'data: {"choices":[{"delta":{"tool_calls":[{"index":0,'
                '"function":{"name":"file","arguments":"\\"README.md\\"}"}}]}}]}'
            ),
            'data: {"choices":[],"usage":{"prompt_tokens":11,"completion_tokens":4}}',
            "data: [DONE]",
            "",
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["stream"] is True
        assert body["stream_options"] == {"include_usage": True}
        return httpx.Response(200, text=stream_body, headers={"content-type": "text/event-stream"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider(
        api_key="secret",
        base_url="https://example.test/v1",
        model="test-model",
        client=client,
    )

    chunks = [
        chunk
        async for chunk in provider.stream_complete(
            [Message(role="user", content="inspect")],
            [
                ToolSchema(
                    name="read_file",
                    description="Read a file",
                    parameters={"type": "object"},
                )
            ],
        )
    ]
    await client.aclose()

    assert [chunk.delta for chunk in chunks if chunk.delta] == ["Hello ", "world"]
    response = chunks[-1].response
    assert response is not None
    assert response.content == "Hello world"
    assert response.tool_calls[0].name == "read_file"
    assert response.tool_calls[0].arguments == {"path": "README.md"}
    assert response.usage.total_tokens == 15
