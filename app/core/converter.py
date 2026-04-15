"""转换器抽象基类"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

TRequest = TypeVar("TRequest")    # 源协议请求类型
TResponse = TypeVar("TResponse")  # 目标协议响应类型
TEvent = TypeVar("TEvent")        # 目标协议流式事件类型


class BaseConverter(ABC, Generic[TRequest, TResponse, TEvent]):
    """转换器抽象接口，所有转换器实现必须继承此类并指定泛型参数。"""

    @abstractmethod
    def convert_request(self, request: TRequest) -> Any:
        """将源协议请求转换为目标协议请求。"""
        ...

    @abstractmethod
    def convert_response(self, response: TResponse) -> Any:
        """将目标协议响应转换为源协议响应。"""
        ...

    @abstractmethod
    def convert_stream_event(self, event: TEvent, state: dict) -> list:
        """将目标协议流式事件转换为源协议流式事件列表。"""
        ...
