"""OpenAI API 客户端 — 基于官方 openai SDK"""

from __future__ import annotations

from typing import Any

import openai

from app.core.client import BaseClient
from app.core.config import get_settings


class OpenAIClient(BaseClient):
    """封装 openai.AsyncOpenAI，实现 BaseClient 接口。"""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url

    async def send(
        self, params: Any, api_key: str, stream: bool = False
    ) -> Any:
        """
        发送请求到 OpenAI Chat Completions API。
        非流式返回 openai.types.chat.ChatCompletion，
        流式返回 openai.AsyncStream[ChatCompletionChunk]。
        """
        client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url=self.base_url,
        )

        params["stream"] = stream
        return await client.chat.completions.create(**params)
