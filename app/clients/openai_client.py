"""OpenAI API 客户端"""

from __future__ import annotations

from typing import AsyncIterator

import httpx

from app.core.config import get_settings

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0))
    return _client


async def send(request_body: dict, api_key: str, stream: bool = False) -> dict | AsyncIterator[str]:
    """
    发送请求到 OpenAI Chat Completions API。
    非流式返回 dict，流式返回逐行 AsyncIterator[str]。
    """
    settings = get_settings()
    url = f"{settings.openai_base_url}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "content-type": "application/json",
    }

    print(f"[DEBUG] openai_client.send -> url: {url}")
    print(f"[DEBUG] openai_client.send -> headers: {headers}")
    print(f"[DEBUG] openai_client.send -> body: {request_body}")
    print(f"[DEBUG] openai_client.send -> stream: {stream}")

    client = _get_client()

    try:
        if not stream:
            resp = await client.post(url, json=request_body, headers=headers)
            print(f"[DEBUG] openai_client.send -> response status: {resp.status_code}")
            print(f"[DEBUG] openai_client.send -> response body: {resp.text[:500]}")
            resp.raise_for_status()
            return resp.json()

        # 流式
        req = client.build_request("POST", url, json=request_body, headers=headers)
        resp = await client.send(req, stream=True)
        print(f"[DEBUG] openai_client.send -> stream response status: {resp.status_code}")
        if resp.status_code >= 400:
            await resp.aread()
            print(f"[DEBUG] openai_client.send -> stream error body: {resp.text[:500]}")
            resp.raise_for_status()
        return _iter_sse(resp)
    except Exception as e:
        print(f"[DEBUG] openai_client.send -> exception: {type(e).__name__}: {e}")
        raise


async def _iter_sse(resp: httpx.Response) -> AsyncIterator[str]:
    """逐行迭代 SSE 响应，yield 每个 data: 行的内容"""
    buffer = ""
    async for chunk in resp.aiter_text():
        buffer += chunk
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            line = line.strip()
            if line.startswith("data: "):
                yield line  # 保留 "data: " 前缀，与 claude_to_openai 转换器配合
    if buffer.strip():
        if buffer.strip().startswith("data: "):
            yield buffer.strip()
