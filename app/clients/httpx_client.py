"""通用 HTTP 客户端 — 基于 common.http.HttpClient"""

from __future__ import annotations

from typing import AsyncIterator

from app.core.client import BaseClient
from common.http import HttpClient
from common.routes import ROUTE_PATHS, auth_headers


class HttpxClient(BaseClient):
    """通用 HTTP 客户端，不依赖任何 SDK，直接发送 HTTP 请求。

    根据 interface 拼接上游 URL 路径，根据 interface 决定认证头格式。
    非流式返回 dict，流式透传上游 SSE data str。
    """

    async def chat(
        self, params: dict, api_key: str, stream: bool = False
    ) -> dict | AsyncIterator[str]:
        http = HttpClient(base_url=self.base_url, headers=auth_headers(self.interface, api_key))
        path = ROUTE_PATHS[self.interface]
        if not stream:
            return await http.post_json(path, params)
        return http.iter_sse(path, {**params, "stream": True})
