"""CLI HTTP 客户端 — 向 Proxy 服务发送请求"""

from __future__ import annotations

import json
from typing import AsyncIterator

import httpx


# 路由 → URL 路径 + 认证头
ROUTE_CONFIG = {
    "completions": {
        "path": "/v1/chat/completions",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
    },
    "messages": {
        "path": "/v1/messages",
        "auth_header": "x-api-key",
        "auth_prefix": "",
    },
    "responses": {
        "path": "/v1/responses",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
    },
}


class ChatClient:
    """向目标服务发送请求，解析响应。"""

    def __init__(self, base_url: str, route: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.route = route
        self.api_key = api_key

    async def list_models(self) -> list[str] | None:
        """探测可用模型列表，不支持时返回 None。"""
        url = self.base_url + "/v1/models"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=5.0)
                if resp.status_code == 200:
                    data = resp.json()
                    models = data.get("data", [])
                    return [m.get("id", "") for m in models if m.get("id")]
        except Exception:
            pass
        return None

    async def send(
        self, messages: list[dict], model: str, stream: bool = False
    ) -> dict:
        """发送非流式对话请求，返回解析后的响应。"""
        url, headers, body = self._build_request(messages, model, stream=False)
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=body, headers=headers, timeout=120.0)
            resp.raise_for_status()
            return resp.json()

    async def send_stream(
        self, messages: list[dict], model: str
    ) -> AsyncIterator[str]:
        """发送流式请求，yield SSE data 行。"""
        url, headers, body = self._build_request(messages, model, stream=True)
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST", url, json=body, headers=headers, timeout=120.0
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            return
                        yield data
                    elif line.startswith("data:"):
                        data = line[5:].strip()
                        if data == "[DONE]":
                            return
                        yield data

    def _build_request(
        self, messages: list[dict], model: str, stream: bool
    ) -> tuple[str, dict, dict]:
        """根据路由构建 URL / headers / body。"""
        rc = ROUTE_CONFIG[self.route]
        url = self.base_url + rc["path"]
        headers = {
            "Content-Type": "application/json",
            rc["auth_header"]: rc["auth_prefix"] + self.api_key,
        }

        if self.route == "responses":
            # Responses 格式：input + instructions
            body = {"model": model, "input": messages, "stream": stream}
        else:
            # Completions / Messages 格式
            body = {"model": model, "messages": messages, "stream": stream}
            if self.route == "messages":
                body["max_tokens"] = 4096

        return url, headers, body

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
