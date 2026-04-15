"""OpenAI 兼容路由集成测试"""

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
async def test_missing_auth(client):
    resp = await client.post("/v1/chat/completions", json={"model": "gpt-4o", "messages": []})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_non_stream(client):
    # 构造 mock anthropic.types.Message
    mock_msg = MagicMock()
    mock_msg.id = "msg_test123"
    mock_msg.model = "claude-sonnet-4-6-20250514"
    mock_text = MagicMock()
    mock_text.type = "text"
    mock_text.text = "Hi from Claude!"
    mock_msg.content = [mock_text]
    mock_msg.stop_reason = "end_turn"
    mock_usage = MagicMock()
    mock_usage.input_tokens = 10
    mock_usage.output_tokens = 5
    mock_msg.usage = mock_usage

    with patch("app.clients.claude_client.ClaudeClient.send", new_callable=AsyncMock, return_value=mock_msg):
        resp = await client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hello"}]},
            headers={"Authorization": "Bearer sk-test-key"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["choices"][0]["message"]["content"] == "Hi from Claude!"
    assert data["choices"][0]["finish_reason"] == "stop"
    assert data["id"].startswith("chatcmpl-")


@pytest.mark.asyncio
async def test_key_passthrough(client):
    mock_msg = MagicMock()
    mock_msg.id = "msg_x"
    mock_msg.model = "m"
    mock_text = MagicMock()
    mock_text.type = "text"
    mock_text.text = "ok"
    mock_msg.content = [mock_text]
    mock_msg.stop_reason = "end_turn"
    mock_usage = MagicMock()
    mock_usage.input_tokens = 1
    mock_usage.output_tokens = 1
    mock_msg.usage = mock_usage

    with patch("app.clients.claude_client.ClaudeClient.send", new_callable=AsyncMock, return_value=mock_msg) as mock_send:
        await client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
            headers={"Authorization": "Bearer sk-my-secret"},
        )
        mock_send.assert_called_once()
        assert mock_send.call_args.kwargs["api_key"] == "sk-my-secret"
