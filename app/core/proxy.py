"""Proxy 调度核心 + ProxyRegistry 容器"""

from __future__ import annotations

from typing import Any, AsyncIterator

from app.core.client import BaseClient
from app.core.converter import BaseConverter


class Proxy:
    """客户端 + 转换器的组合，封装完整的 请求转换 → 上游调用 → 响应转换 流程。

    Client 返回 SDK 原始对象，Proxy 直接透传给 Converter 处理。
    路由层只需调用 chat()，不关心内部编排。
    """

    def __init__(self, client: BaseClient, converter: BaseConverter):
        self.client = client
        self.converter = converter

    async def chat(
        self, body: dict, api_key: str, stream: bool = False
    ) -> str | AsyncIterator[str]:
        """统一调度入口。

        Args:
            body: 下游原始请求（dict）
            api_key: 认证密钥
            stream: 是否流式

        Returns:
            非流式: str（JSON 字符串，已转换为下游格式）
            流式:   AsyncIterator[str]（已转换为下游格式的 SSE data）
        """
        req = self.converter.convert_request(body)

        if not stream:
            raw = await self.client.chat(req, api_key, stream=False)
            return self.converter.convert_response(raw)
        else:
            upstream = await self.client.chat(req, api_key, stream=True)
            return self._stream(upstream)

    async def _stream(self, upstream: AsyncIterator) -> AsyncIterator[str]:
        """流式转换：直接把 Client 事件传给 Converter，流结束后调用 convert_stream_done（如有）。"""
        async for event in upstream:
            for item in self.converter.convert_stream_event(event):
                yield item
        if hasattr(self.converter, "convert_stream_done"):
            for item in self.converter.convert_stream_done():
                yield item


class ProxyRegistry:
    """Proxy 容器，按接口名管理。"""

    def __init__(self) -> None:
        self._proxies: dict[str, Proxy] = {}

    def add(self, name: str, proxy: Proxy) -> None:
        """注册一个 Proxy。"""
        self._proxies[name] = proxy

    def get(self, name: str) -> Proxy:
        """获取指定 Proxy，不存在时抛出 KeyError。"""
        if name not in self._proxies:
            raise KeyError(
                f"Proxy '{name}' not registered. Available: {self.list()}"
            )
        return self._proxies[name]

    def list(self) -> list[str]:
        """列出所有已注册的 Proxy 名称。"""
        return list(self._proxies.keys())


# 全局注册表实例
registry = ProxyRegistry()
