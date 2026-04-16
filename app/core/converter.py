"""转换器抽象基类"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any


class BaseConverter(ABC):
    """格式转换器抽象接口。

    接收 SDK 原始对象或 dict/str，输出统一为 str。
    各子类通过明确的类型注解声明接收的 SDK 类型。
    """

    @abstractmethod
    def convert_request(self, request: dict) -> dict:
        """将下游请求转换为上游请求参数。"""
        ...

    @abstractmethod
    def convert_response(self, response) -> str:
        """将上游响应转换为下游响应 JSON 字符串。"""
        ...

    @abstractmethod
    def convert_stream_event(self, event) -> list[str]:
        """将上游事件转换为下游 SSE data 字符串列表。"""
        ...

    @staticmethod
    def _to_dict(raw) -> dict:
        """SDK 对象 / dict / str → dict。"""
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            return json.loads(raw)
        if hasattr(raw, "model_dump"):
            return raw.model_dump(mode="json")
        return raw
