"""Claude 兼容路由集成测试"""

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice
from openai.types import CompletionUsage

from main import app


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_missing_api_key(client):
    resp = await client.post("/v1/messages", json={
        "model": "claude-sonnet-4-6-20250514",
        "messages": [{"role": "user", "content": "Hi"}],
        "max_tokens": 1024,
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_non_stream(client):
    mock_resp = ChatCompletion(
        id="chatcmpl-test456",
        object="chat.completion",
        created=0,
        model="gpt-4o",
        choices=[Choice(
            index=0,
            message=ChatCompletionMessage(role="assistant", content="Hi from OpenAI!"),
            finish_reason="stop",
        )],
        usage=CompletionUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )

    with patch("app.clients.openai_client.OpenAIClient.send", new_callable=AsyncMock, return_value=mock_resp):
        resp = await client.post(
            "/v1/messages",
            json={
                "model": "claude-sonnet-4-6-20250514",
                "messages": [{"role": "user", "content": "Hello"}],
                "max_tokens": 1024,
            },
            headers={"x-api-key": "sk-ant-test-key"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["content"][0]["text"] == "Hi from OpenAI!"
    assert data["stop_reason"] == "end_turn"
    assert data["type"] == "message"


@pytest.mark.asyncio
async def test_key_passthrough(client):
    mock_resp = ChatCompletion(
        id="chatcmpl-x",
        object="chat.completion",
        created=0,
        model="gpt-4o",
        choices=[Choice(
            index=0,
            message=ChatCompletionMessage(role="assistant", content="ok"),
            finish_reason="stop",
        )],
        usage=CompletionUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
    )

    with patch("app.clients.openai_client.OpenAIClient.send", new_callable=AsyncMock, return_value=mock_resp) as mock_send:
        await client.post(
            "/v1/messages",
            json={
                "model": "claude-sonnet-4-6-20250514",
                "messages": [{"role": "user", "content": "Hi"}],
                "max_tokens": 1024,
            },
            headers={"x-api-key": "sk-ant-my-secret"},
        )
        mock_send.assert_called_once()
        assert mock_send.call_args.kwargs["api_key"] == "sk-ant-my-secret"
