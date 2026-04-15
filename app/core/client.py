"""客户端抽象基类"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseClient(ABC):
    """客户端抽象接口，所有客户端实现必须继承此类。"""

    @abstractmethod
    async def send(
        self, params: dict, api_key: str, stream: bool = False
    ) -> Any:
        """发送请求到上游 API。非流式返回响应对象，流式返回异步迭代器。"""
        ...
