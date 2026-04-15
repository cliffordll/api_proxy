"""Claude (Anthropic) API 客户端"""

from __future__ import annotations

from typing import AsyncIterator

import httpx

from app.core.config import get_settings

ANTHROPIC_VERSION = "2023-06-01"

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0))
    return _client


async def send(request_body: dict, api_key: str, stream: bool = False) -> dict | AsyncIterator[str]:
    """
    发送请求到 Claude Messages API。
    非流式返回 dict，流式返回逐行 AsyncIterator[str]。
    """
    settings = get_settings()
    url = f"{settings.anthropic_base_url}/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }

    client = _get_client()

    if not stream:
        resp = await client.post(url, json=request_body, headers=headers)
        resp.raise_for_status()
        return resp.json()

    # 流式
    req = client.build_request("POST", url, json=request_body, headers=headers)
    resp = await client.send(req, stream=True)
    if resp.status_code >= 400:
        await resp.aread()
        resp.raise_for_status()
    return _iter_sse(resp)


async def _iter_sse(resp: httpx.Response) -> AsyncIterator[str]:
    """逐行迭代 SSE 响应，yield 完整的 event 块"""
    buffer = ""
    async for chunk in resp.aiter_text():
        buffer += chunk
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            line = line.strip()
            if line.startswith("data: "):
                yield line[6:]
            elif line.startswith("event: "):
                pass  # event type 行，用于辅助解析
    if buffer.strip():
        if buffer.strip().startswith("data: "):
            yield buffer.strip()[6:]
