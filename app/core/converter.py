"""转换器抽象基类"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseConverter(ABC):
    """转换器抽象接口，所有转换器实现必须继承此类。"""

    @abstractmethod
    def convert_request(self, request: dict) -> dict:
        """将源协议请求转换为目标协议请求。"""
        ...

    @abstractmethod
    def convert_response(self, response: Any) -> dict:
        """将目标协议响应转换为源协议响应。"""
        ...

    @abstractmethod
    def convert_stream_event(self, event: Any, state: dict) -> list:
        """将目标协议流式事件转换为源协议流式事件列表。"""
        ...
