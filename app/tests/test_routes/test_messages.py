"""messages 路由测试"""

import pytest
from httpx import ASGITransport, AsyncClient
from app.server import app


@pytest.mark.asyncio
async def test_no_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/v1/messages", json={"model": "claude", "messages": [], "max_tokens": 100})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_non_stream():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/v1/messages",
            headers={"x-api-key": "fake-key"},
            json={"model": "claude-sonnet-4-6-20250514", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 100})
    assert r.status_code == 200
    data = r.json()
    assert "content" in data
    assert data["type"] == "message"
