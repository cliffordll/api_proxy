"""Claude 兼容路由集成测试"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

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
    # 构造 mock openai.types.chat.ChatCompletion
    mock_resp = MagicMock()
    mock_resp.id = "chatcmpl-test456"
    mock_resp.model = "gpt-4o"

    mock_message = MagicMock()
    mock_message.content = "Hi from OpenAI!"
    mock_message.tool_calls = None

    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_choice.finish_reason = "stop"

    mock_resp.choices = [mock_choice]

    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 10
    mock_usage.completion_tokens = 5
    mock_resp.usage = mock_usage

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
    mock_resp = MagicMock()
    mock_resp.id = "chatcmpl-x"
    mock_resp.model = "gpt-4o"

    mock_message = MagicMock()
    mock_message.content = "ok"
    mock_message.tool_calls = None

    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_choice.finish_reason = "stop"

    mock_resp.choices = [mock_choice]

    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 1
    mock_usage.completion_tokens = 1
    mock_resp.usage = mock_usage

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
