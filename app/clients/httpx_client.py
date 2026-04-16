"""通用 HTTP 客户端 — 基于 httpx.AsyncClient"""

from __future__ import annotations

from typing import AsyncIterator

import httpx

from app.core.client import BaseClient


class HttpxClient(BaseClient):
    """通用 HTTP 客户端，不依赖任何 SDK，直接发送 HTTP 请求。

    根据 interface 拼接上游 URL 路径，根据 interface 决定认证头格式。
    非流式返回 dict，流式透传上游 SSE data str。
    """

    INTERFACE_PATHS = {
        "messages": "/v1/messages",
        "completions": "/v1/chat/completions",
        "responses": "/v1/responses",
    }

    async def chat(
        self, params: dict, api_key: str, stream: bool = False
    ) -> dict | AsyncIterator[str]:
        url = self.base_url.rstrip("/") + self.INTERFACE_PATHS[self.interface]
        headers = self._build_headers(api_key)

        if not stream:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    url, json=params, headers=headers, timeout=120.0
                )
                resp.raise_for_status()
                return resp.json()
        else:
            params = {**params, "stream": True}
            return self._stream_chat(url, params, headers)

    async def _stream_chat(
        self, url: str, params: dict, headers: dict
    ) -> AsyncIterator[str]:
        """流式调用，逐行读取上游 SSE，透传 data 内容。"""
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST", url, json=params, headers=headers, timeout=120.0
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        yield line[6:]  # 去掉 "data: " 前缀

    def _build_headers(self, api_key: str) -> dict[str, str]:
        """根据 interface 决定认证头格式。"""
        headers = {"Content-Type": "application/json"}
        if self.interface == "messages":
            # Claude Messages API 风格
            headers["x-api-key"] = api_key
            headers["anthropic-version"] = "2023-06-01"
        else:
            # OpenAI 风格
            headers["Authorization"] = f"Bearer {api_key}"
        return headers
