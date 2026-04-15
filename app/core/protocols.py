"""抽象接口定义：BaseClient 和 BaseConverter Protocol"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class BaseClient(Protocol):
    """客户端抽象接口"""

    async def send(
        self, params: dict, api_key: str, stream: bool = False
    ) -> Any:
        """发送请求到上游 API。非流式返回响应对象，流式返回异步迭代器。"""
        ...


@runtime_checkable
class BaseConverter(Protocol):
    """转换器抽象接口"""

    def convert_request(self, request: dict) -> dict:
        """将源协议请求转换为目标协议请求。"""
        ...

    def convert_response(self, response: Any) -> dict:
        """将目标协议响应转换为源协议响应。"""
        ...

    def convert_stream_event(self, event: Any, state: dict) -> list:
        """将目标协议流式事件转换为源协议流式事件列表。"""
        ...
