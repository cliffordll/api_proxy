"""Claude (Anthropic) API 客户端 — 基于官方 anthropic SDK"""

from __future__ import annotations

import json
from typing import AsyncIterator

import anthropic

from app.core.client import BaseClient


class ClaudeClient(BaseClient):
    """封装 anthropic.AsyncAnthropic，统一 chat() 接口。

    interface 固定为 "messages"。
    非流式返回 dict，流式 yield SSE data str。
    """

    async def chat(
        self, params: dict, api_key: str, stream: bool = False
    ) -> dict | AsyncIterator[str]:
        client = anthropic.AsyncAnthropic(
            api_key=api_key,
            base_url=self.base_url,
        )

        # 移除 stream 字段，由方法参数控制
        params = {k: v for k, v in params.items() if k != "stream"}

        if not stream:
            response = await client.messages.create(**params)
            return response.model_dump(mode="json")
        else:
            return self._stream_chat(client, params)

    async def _stream_chat(
        self, client: anthropic.AsyncAnthropic, params: dict
    ) -> AsyncIterator[str]:
        """流式调用，逐事件 yield JSON 字符串。"""
        stream = await client.messages.create(stream=True, **params)
        async for event in stream:
            yield json.dumps(event.model_dump(mode="json"), ensure_ascii=False)
