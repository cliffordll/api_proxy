"""Proxy + ProxyRegistry 单元测试"""

import pytest
import asyncio

from app.core.client import BaseClient
from app.core.converter import BaseConverter
from app.core.proxy import Proxy, ProxyRegistry


class StubClient(BaseClient):
    async def chat(self, params, api_key, stream=False):
        if not stream:
            return {"echo": params, "key": api_key}
        return self._gen(params)

    async def _gen(self, params):
        yield '{"type":"chunk","text":"hello"}'
        yield '{"type":"chunk","text":"world"}'


class StubConverter(BaseConverter):
    def convert_request(self, request):
        return {**request, "converted": True}

    def convert_response(self, response):
        return {**response, "output_converted": True}

    def convert_stream_event(self, data):
        return [f"[converted]{data}"]


class TestProxyRegistry:
    def test_add_and_get(self):
        reg = ProxyRegistry()
        proxy = Proxy(StubClient("http://x", "messages"), StubConverter())
        reg.add("test", proxy)
        assert reg.get("test") is proxy

    def test_get_not_registered_raises(self):
        reg = ProxyRegistry()
        with pytest.raises(KeyError, match="not registered"):
            reg.get("nonexistent")

    def test_list_empty(self):
        assert ProxyRegistry().list() == []

    def test_list(self):
        reg = ProxyRegistry()
        proxy = Proxy(StubClient("http://x", "messages"), StubConverter())
        reg.add("a", proxy)
        reg.add("b", proxy)
        assert sorted(reg.list()) == ["a", "b"]

    def test_overwrite(self):
        reg = ProxyRegistry()
        p1 = Proxy(StubClient("http://x", "messages"), StubConverter())
        p2 = Proxy(StubClient("http://y", "messages"), StubConverter())
        reg.add("x", p1)
        reg.add("x", p2)
        assert reg.get("x") is p2


class TestProxy:
    @pytest.mark.asyncio
    async def test_non_stream(self):
        proxy = Proxy(StubClient("http://x", "messages"), StubConverter())
        result = await proxy.chat({"model": "test"}, "key123", stream=False)
        assert result["output_converted"] is True
        assert result["echo"]["converted"] is True
        assert result["key"] == "key123"

    @pytest.mark.asyncio
    async def test_stream(self):
        proxy = Proxy(StubClient("http://x", "messages"), StubConverter())
        stream = await proxy.chat({"model": "test"}, "key123", stream=True)
        items = [item async for item in stream]
        assert len(items) == 2
        assert all(item.startswith("[converted]") for item in items)
