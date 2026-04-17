"""HTTP 客户端 — 模仿 openai / anthropic SDK 风格的 httpx 薄封装

用法：
    http = HttpClient(base_url="http://host/v1", headers={"Authorization": "Bearer ..."})
    data = await http.get_json("/models", swallow_errors=True)
    resp = await http.post_json("/chat/completions", body={...})
    async for data in http.iter_sse("/chat/completions", body={...}):
        ...

说明：
  - 每次调用内部新建 `httpx.AsyncClient`，无长连接池（符合当前规模与短生命周期场景）
  - path 为绝对 URL 时直接使用，否则拼接 base_url
  - `[DONE]` 哨兵由调用方自行过滤
"""

from __future__ import annotations

from typing import AsyncIterator

import httpx


class HttpClient:
    """HTTP 客户端，持 base_url + 默认 headers，支持 GET / POST / SSE 流式。"""

    DEFAULT_GET_TIMEOUT = 5.0
    DEFAULT_POST_TIMEOUT = 120.0

    def __init__(self, base_url: str = "", headers: dict | None = None):
        self.base_url = base_url.rstrip("/") if base_url else ""
        self.headers = headers or {}

    def _url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if not path.startswith("/"):
            path = "/" + path
        return self.base_url + path

    async def get_json(
        self,
        path: str,
        timeout: float = DEFAULT_GET_TIMEOUT,
        swallow_errors: bool = False,
    ) -> dict | None:
        """GET 请求返回 JSON。swallow_errors=True 时任何失败返回 None。"""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(self._url(path), headers=self.headers, timeout=timeout)
                if swallow_errors and resp.status_code != 200:
                    return None
                resp.raise_for_status()
                return resp.json()
        except Exception:
            if swallow_errors:
                return None
            raise

    async def post_json(
        self,
        path: str,
        body: dict,
        timeout: float = DEFAULT_POST_TIMEOUT,
    ) -> dict:
        """POST JSON，raise_for_status，返回 JSON。"""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self._url(path), json=body, headers=self.headers, timeout=timeout
            )
            resp.raise_for_status()
            return resp.json()

    async def iter_sse(
        self,
        path: str,
        body: dict,
        timeout: float = DEFAULT_POST_TIMEOUT,
        skip_done: bool = False,
    ) -> AsyncIterator[str]:
        """POST 流式，逐行读取上游 SSE，yield `data:` 字段内容（剥前缀 + 去前导空白）。

        skip_done=True 时过滤 `[DONE]` 哨兵（OpenAI 兼容流常见终止符）。
        """
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST", self._url(path), json=body, headers=self.headers, timeout=timeout
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if line.startswith("data:"):
                        data = line[5:].lstrip()
                        if skip_done and data == "[DONE]":
                            return
                        yield data
