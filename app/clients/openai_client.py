"""OpenAI API 客户端 — 基于官方 openai SDK"""

from __future__ import annotations

from typing import Any, AsyncIterator

import openai

from app.core.client import BaseClient


class OpenAIClient(BaseClient):
    """封装 openai.AsyncOpenAI，统一 chat() 接口。

    interface 为 "completions" 或 "responses"，决定调哪个 SDK 方法。
    返回 SDK 原始对象，不做序列化。
    """

    async def chat(
        self, params: dict, api_key: str, stream: bool = False
    ) -> Any:
        client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url=self.base_url,
        )

        # 移除 stream 字段，由方法参数控制
        params = {k: v for k, v in params.items() if k != "stream"}

        if self.interface == "completions":
            return await self._chat_completions(client, params, stream)
        elif self.interface == "responses":
            return await self._chat_responses(client, params, stream)
        else:
            raise ValueError(f"Unsupported interface: {self.interface}")

    async def _chat_completions(
        self, client: openai.AsyncOpenAI, params: dict, stream: bool
    ) -> Any:
        if not stream:
            return await client.chat.completions.create(**params)
        else:
            return self._stream_completions(client, params)

    async def _stream_completions(
        self, client: openai.AsyncOpenAI, params: dict
    ) -> AsyncIterator:
        stream = await client.chat.completions.create(stream=True, **params)
        async for chunk in stream:
            yield chunk

    async def _chat_responses(
        self, client: openai.AsyncOpenAI, params: dict, stream: bool
    ) -> Any:
        if not stream:
            return await client.responses.create(**params)
        else:
            return self._stream_responses(client, params)

    async def _stream_responses(
        self, client: openai.AsyncOpenAI, params: dict
    ) -> AsyncIterator:
        stream = await client.responses.create(stream=True, **params)
        async for event in stream:
            yield event
