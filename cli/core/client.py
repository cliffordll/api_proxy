"""CLI HTTP 客户端 — 向 Proxy 服务发送请求"""

from __future__ import annotations

import json
from typing import AsyncIterator

from common.http import HttpClient
from common.routes import ROUTE_PATHS, auth_headers


class ChatClient:
    """向目标服务发送请求，解析响应。"""

    def __init__(self, base_url: str, route: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.route = route
        self.api_key = api_key
        self._path = ROUTE_PATHS[route]
        self._http = HttpClient(base_url=self.base_url, headers=auth_headers(route, api_key))

    async def send(
        self, messages: list[dict], model: str, stream: bool = False
    ) -> dict:
        """发送非流式对话请求，返回解析后的响应。"""
        return await self._http.post_json(self._path, self._build_body(messages, model, stream=False))

    async def send_stream(
        self, messages: list[dict], model: str
    ) -> AsyncIterator[str]:
        """发送流式请求，yield SSE data 字段（过滤 [DONE] 哨兵）。"""
        async for data in self._http.iter_sse(
            self._path, self._build_body(messages, model, stream=True), skip_done=True
        ):
            yield data

    def _build_body(self, messages: list[dict], model: str, stream: bool) -> dict:
        """根据路由构建请求体。"""
        if self.route == "responses":
            # Responses 格式：input + instructions
            return {"model": model, "input": messages, "stream": stream}
        # Completions / Messages 格式
        body = {"model": model, "messages": messages, "stream": stream}
        if self.route == "messages":
            body["max_tokens"] = 4096
        return body

    def parse_response(self, data: dict) -> tuple[str, list[dict] | None]:
        """从响应中提取文本和 tool_calls。

        Returns:
            (text, tool_calls) — tool_calls 为 None 表示无工具调用
        """
        if self.route == "completions":
            msg = data["choices"][0]["message"]
            return msg.get("content") or "", msg.get("tool_calls")
        elif self.route == "messages":
            text_parts = []
            tool_calls = []
            for block in data.get("content", []):
                if block["type"] == "text":
                    text_parts.append(block["text"])
                elif block["type"] == "tool_use":
                    tool_calls.append(block)
            return "\n".join(text_parts), tool_calls or None
        elif self.route == "responses":
            text_parts = []
            tool_calls = []
            for item in data.get("output", []):
                if item["type"] == "message":
                    for part in item.get("content", []):
                        if part.get("type") == "output_text":
                            text_parts.append(part["text"])
                elif item["type"] == "function_call":
                    tool_calls.append(item)
            return "\n".join(text_parts), tool_calls or None
        return "", None

    def parse_stream_chunk(self, data: str) -> str | None:
        """从 SSE data 中提取增量文本。"""
        try:
            obj = json.loads(data)
        except json.JSONDecodeError:
            return None

        if self.route == "completions":
            choices = obj.get("choices", [])
            if choices:
                delta = choices[0].get("delta", {})
                return delta.get("content")
        elif self.route == "messages":
            if obj.get("type") == "content_block_delta":
                delta = obj.get("delta", {})
                if delta.get("type") == "text_delta":
                    return delta.get("text")
        elif self.route == "responses":
            if obj.get("type") == "response.output_text.delta":
                return obj.get("delta")
        return None
