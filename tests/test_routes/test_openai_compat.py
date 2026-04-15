"""OpenAI 兼容路由集成测试"""

import json
from unittest.mock import AsyncMock, patch

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
    mock_claude_resp = {
        "id": "msg_test123",
        "model": "claude-sonnet-4-6-20250514",
        "content": [{"type": "text", "text": "Hi from Claude!"}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }

    with patch("app.clients.claude_client.send", new_callable=AsyncMock, return_value=mock_claude_resp):
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
async def test_stream(client):
    async def mock_stream(*args, **kwargs):
        events = [
            '{"type":"message_start","message":{"id":"msg_s1","model":"claude-sonnet-4-6-20250514"}}',
            '{"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hello"}}',
            '{"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":1}}',
            '{"type":"message_stop"}',
        ]
        for e in events:
            yield e

    with patch("app.clients.claude_client.send", new_callable=AsyncMock, return_value=mock_stream()):
        resp = await client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hello"}], "stream": True},
            headers={"Authorization": "Bearer sk-test-key"},
        )

    assert resp.status_code == 200
    body = resp.text
    assert "data: " in body
    assert "[DONE]" in body


@pytest.mark.asyncio
async def test_key_passthrough(client):
    with patch("app.clients.claude_client.send", new_callable=AsyncMock, return_value={
        "id": "msg_x", "model": "m", "content": [{"type": "text", "text": "ok"}],
        "stop_reason": "end_turn", "usage": {"input_tokens": 1, "output_tokens": 1},
    }) as mock_send:
        await client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "Hi"}]},
            headers={"Authorization": "Bearer sk-my-secret"},
        )
        mock_send.assert_called_once()
        assert mock_send.call_args.kwargs["api_key"] == "sk-my-secret"
