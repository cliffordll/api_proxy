"""responses 路由测试"""

import pytest
from httpx import ASGITransport, AsyncClient
from app.server import app


@pytest.mark.asyncio
async def test_no_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/v1/responses", json={"model": "gpt-4o", "input": "hi"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_non_stream():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/v1/responses",
            headers={"Authorization": "Bearer fake-key"},
            json={"model": "gpt-4o", "input": "hi"})
    assert r.status_code == 200
    data = r.json()
    assert "output" in data
    assert data["status"] == "completed"
