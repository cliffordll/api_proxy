"""客户端抽象基类"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator


class BaseClient(ABC):
    """供应商客户端抽象接口。

    统一传输层：输入 dict，输出 dict（非流式）或 AsyncIterator[str]（流式 SSE data）。
    SDK 细节封装在各子类内部，对外只暴露 dict/str。
    """

    def __init__(self, base_url: str, interface: str):
        self.base_url = base_url
        self.interface = interface  # "messages" / "completions" / "responses"

    @abstractmethod
    async def chat(
        self, params: dict, api_key: str, stream: bool = False
    ) -> dict | AsyncIterator[str]:
        """发送请求到上游 API。

        Args:
            params: 上游请求参数（dict）
            api_key: 认证密钥
            stream: 是否流式

        Returns:
            非流式: dict（上游 JSON 响应）
            流式:   AsyncIterator[str]（SSE data 内容，不含 "data: " 前缀）
        """
        ...
