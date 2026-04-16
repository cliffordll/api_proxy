"""透传转换器 — 不做格式转换，直接转发"""

from __future__ import annotations

import json

from app.core.converter import BaseConverter


class PassthroughConverter(BaseConverter):
    """透传转换器，请求原样发、响应原样回。

    converter 未配置时自动使用。
    """

    def convert_request(self, request: dict) -> dict:
        return request

    def convert_response(self, response) -> str:
        data = self._to_dict(response)
        return json.dumps(data, ensure_ascii=False)

    def convert_stream_event(self, event) -> list[str]:
        if isinstance(event, str):
            data = event.strip()
        else:
            data = json.dumps(self._to_dict(event), ensure_ascii=False)

        if data == "[DONE]":
            return ["data: [DONE]\n\n"]

        # 检测 type 字段决定 SSE 格式
        try:
            obj = json.loads(data)
            event_type = obj.get("type", "")
        except (json.JSONDecodeError, AttributeError):
            event_type = ""

        if event_type:
            return [f"event: {event_type}\ndata: {data}\n\n"]
        else:
            return [f"data: {data}\n\n"]
