"""OpenAI API 客户端 — 基于官方 openai SDK"""

from __future__ import annotations

import json
from typing import AsyncIterator

import openai

from app.core.client import BaseClient


class OpenAIClient(BaseClient):
    """封装 openai.AsyncOpenAI，统一 chat() 接口。

    interface 为 "completions" 或 "responses"，决定调哪个 SDK 方法。
    非流式返回 dict，流式 yield SSE data str。
    """

    async def chat(
        self, params: dict, api_key: str, stream: bool = False
    ) -> dict | AsyncIterator[str]:
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
    ) -> dict | AsyncIterator[str]:
        if not stream:
            response = await client.chat.completions.create(**params)
            return response.model_dump(mode="json")
        else:
            return self._stream_completions(client, params)

    async def _stream_completions(
        self, client: openai.AsyncOpenAI, params: dict
    ) -> AsyncIterator[str]:
        stream = await client.chat.completions.create(stream=True, **params)
        async for chunk in stream:
            yield json.dumps(chunk.model_dump(mode="json"), ensure_ascii=False)

    async def _chat_responses(
        self, client: openai.AsyncOpenAI, params: dict, stream: bool
    ) -> dict | AsyncIterator[str]:
        if not stream:
            response = await client.responses.create(**params)
            return response.model_dump(mode="json")
        else:
            return self._stream_responses(client, params)

    async def _stream_responses(
        self, client: openai.AsyncOpenAI, params: dict
    ) -> AsyncIterator[str]:
        stream = await client.responses.create(stream=True, **params)
        async for event in stream:
            yield json.dumps(event.model_dump(mode="json"), ensure_ascii=False)
