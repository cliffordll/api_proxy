"""completions 路由测试"""

import pytest
from httpx import ASGITransport, AsyncClient
from app.server import app


@pytest.mark.asyncio
async def test_no_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/v1/chat/completions", json={"model": "gpt-4o", "messages": []})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_non_stream():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/v1/chat/completions",
            headers={"Authorization": "Bearer fake-key"},
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200
    data = r.json()
    assert "choices" in data
    assert data["choices"][0]["message"]["role"] == "assistant"


@pytest.mark.asyncio
async def test_stream():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        async with c.stream("POST", "/v1/chat/completions",
            headers={"Authorization": "Bearer fake-key"},
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}], "stream": True}) as r:
            assert r.status_code == 200
            lines = []
            async for line in r.aiter_lines():
                if line.startswith("data: "):
                    lines.append(line[6:])
    assert len(lines) > 0
    assert lines[-1] == "[DONE]"
