"""客户端抽象基类"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator


class BaseClient(ABC):
    """供应商客户端抽象接口。

    纯传输层：返回 SDK 原始对象或 dict/str，不做序列化。
    序列化由 Proxy 层统一处理。
    """

    def __init__(self, base_url: str, interface: str):
        self.base_url = base_url
        self.interface = interface  # "messages" / "completions" / "responses"

    @abstractmethod
    async def chat(
        self, params: dict, api_key: str, stream: bool = False
    ) -> Any:
        """发送请求到上游 API。

        Args:
            params: 上游请求参数（dict）
            api_key: 认证密钥
            stream: 是否流式

        Returns:
            非流式: SDK 对象（ClaudeClient/OpenAIClient）或 dict（HttpxClient/MockupClient）
            流式:   AsyncIterator of SDK 事件对象 或 str
        """
        ...
