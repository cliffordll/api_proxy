"""Claude (Anthropic) API 客户端 — 基于官方 anthropic SDK"""

from __future__ import annotations

from typing import Any

import anthropic

from app.core.config import get_settings


class ClaudeClient:
    """封装 anthropic.AsyncAnthropic，实现 BaseClient 接口。"""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url

    async def send(
        self, params: dict, api_key: str, stream: bool = False
    ) -> Any:
        """
        发送请求到 Claude Messages API。
        非流式返回 anthropic.types.Message，
        流式返回 anthropic.MessageStream（上下文管理器）。
        """
        client = anthropic.AsyncAnthropic(
            api_key=api_key,
            base_url=self.base_url,
        )

        if not stream:
            return await client.messages.create(**params)

        # 流式：返回 MessageStream 上下文管理器
        return client.messages.stream(**params)
