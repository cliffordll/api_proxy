"""Claude (Anthropic) API 客户端 — 基于官方 anthropic SDK"""

from __future__ import annotations

from typing import Any, AsyncIterator

import anthropic

from app.core.client import BaseClient


class ClaudeClient(BaseClient):
    """封装 anthropic.AsyncAnthropic，统一 chat() 接口。

    interface 固定为 "messages"。
    返回 SDK 原始对象，不做序列化。
    """

    async def chat(
        self, params: dict, api_key: str, stream: bool = False
    ) -> Any:
        client = anthropic.AsyncAnthropic(
            api_key=api_key,
            base_url=self.base_url,
        )

        # 移除 stream 字段，由方法参数控制
        params = {k: v for k, v in params.items() if k != "stream"}

        if not stream:
            return await client.messages.create(**params)
        else:
            return self._stream_chat(client, params)

    async def _stream_chat(
        self, client: anthropic.AsyncAnthropic, params: dict
    ) -> AsyncIterator:
        """流式调用，逐事件 yield SDK 原始事件对象。"""
        stream = await client.messages.create(stream=True, **params)
        async for event in stream:
            yield event
