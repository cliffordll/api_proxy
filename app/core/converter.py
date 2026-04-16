"""转换器抽象基类"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseConverter(ABC):
    """格式转换器抽象接口。纯格式转换，与供应商无关。输入输出统一为 dict/str。"""

    @abstractmethod
    def convert_request(self, request: dict) -> dict:
        """将下游请求转换为上游请求参数。"""
        ...

    @abstractmethod
    def convert_response(self, response: dict) -> dict:
        """将上游响应转换为下游响应。"""
        ...

    @abstractmethod
    def convert_stream_event(self, data: str) -> list[str]:
        """将上游 SSE data 转换为下游 SSE data 列表。

        Args:
            data: 上游 SSE 的 data 字段内容（JSON 字符串或 [DONE]）
        Returns:
            转换后的 SSE data 列表，空列表表示跳过
        """
        ...
