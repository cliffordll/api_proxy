"""调试模式客户端 — 返回模拟数据，不调用任何外部 API"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import AsyncIterator

from app.core.client import BaseClient


class MockupClient(BaseClient):
    """调试模式客户端，根据 interface 返回对应格式的模拟数据。

    不需要 api_key，不发起网络请求。用于本地开发和调试。
    """

    async def chat(
        self, params: dict, api_key: str, stream: bool = False
    ) -> dict | AsyncIterator[str]:
        if self.interface == "messages":
            return self._mock_messages(params, stream)
        elif self.interface == "completions":
            return self._mock_completions(params, stream)
        elif self.interface == "responses":
            return self._mock_responses(params, stream)
        else:
            raise ValueError(f"Unsupported interface: {self.interface}")

    @staticmethod
    def _j(data: dict) -> str:
        return json.dumps(data, ensure_ascii=False)

    # ── Messages 模拟 ────────────────────────────────────────

    def _mock_messages(self, params: dict, stream: bool) -> dict | AsyncIterator[str]:
        model = params.get("model", "mock-model")
        msg_id = f"msg_{uuid.uuid4().hex[:24]}"
        text = "[mockup] Hello! How can I help you today?"

        if not stream:
            return {
                "id": msg_id, "type": "message", "role": "assistant",
                "model": model,
                "content": [{"type": "text", "text": text}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 5},
            }
        return self._stream_messages(msg_id, model, text)

    async def _stream_messages(self, msg_id: str, model: str, text: str) -> AsyncIterator[str]:
        yield self._j({"type": "message_start", "message": {
            "id": msg_id, "type": "message", "role": "assistant",
            "model": model, "content": [],
            "usage": {"input_tokens": 10, "output_tokens": 0},
        }})
        yield self._j({"type": "content_block_start", "index": 0,
                   "content_block": {"type": "text", "text": ""}})
        for ch in text:
            await asyncio.sleep(0.02)
            yield self._j({"type": "content_block_delta", "index": 0,
                       "delta": {"type": "text_delta", "text": ch}})
        yield self._j({"type": "content_block_stop", "index": 0})
        yield self._j({"type": "message_delta",
                   "delta": {"stop_reason": "end_turn"},
                   "usage": {"output_tokens": len(text)}})
        yield self._j({"type": "message_stop"})

    # ── Completions 模拟 ─────────────────────────────────────

    def _mock_completions(self, params: dict, stream: bool) -> dict | AsyncIterator[str]:
        model = params.get("model", "mock-model")
        chunk_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
        text = "[mockup] Hello! How can I help you today?"

        if not stream:
            return {
                "id": chunk_id, "object": "chat.completion",
                "created": int(time.time()), "model": model,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            }
        return self._stream_completions(chunk_id, model, text)

    async def _stream_completions(self, chunk_id: str, model: str, text: str) -> AsyncIterator[str]:
        yield self._j({"id": chunk_id, "object": "chat.completion.chunk",
                   "created": int(time.time()), "model": model,
                   "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]})
        for ch in text:
            await asyncio.sleep(0.02)
            yield self._j({"id": chunk_id, "object": "chat.completion.chunk",
                       "created": int(time.time()), "model": model,
                       "choices": [{"index": 0, "delta": {"content": ch}, "finish_reason": None}]})
        yield self._j({"id": chunk_id, "object": "chat.completion.chunk",
                   "created": int(time.time()), "model": model,
                   "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                   "usage": {"prompt_tokens": 10, "completion_tokens": len(text), "total_tokens": 10 + len(text)}})
        yield "[DONE]"

    # ── Responses 模拟 ───────────────────────────────────────

    def _mock_responses(self, params: dict, stream: bool) -> dict | AsyncIterator[str]:
        model = params.get("model", "mock-model")
        resp_id = f"resp_{uuid.uuid4().hex[:24]}"
        text = "[mockup] Hello! How can I help you today?"

        if not stream:
            return {
                "id": resp_id, "object": "response",
                "created_at": int(time.time()), "model": model,
                "output": [{"type": "message", "role": "assistant",
                            "content": [{"type": "output_text", "text": text}]}],
                "status": "completed",
                "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
            }
        return self._stream_responses(resp_id, model, text)

    async def _stream_responses(self, resp_id: str, model: str, text: str) -> AsyncIterator[str]:
        resp_obj = {"id": resp_id, "object": "response", "created_at": int(time.time()),
                     "model": model, "status": "in_progress", "output": []}
        yield self._j({"type": "response.created", "response": resp_obj})
        yield self._j({"type": "response.in_progress", "response": resp_obj})
        yield self._j({"type": "response.output_item.added", "output_index": 0,
                   "item": {"type": "message", "role": "assistant",
                            "content": [{"type": "output_text", "text": ""}]}})
        for ch in text:
            await asyncio.sleep(0.02)
            yield self._j({"type": "response.output_text.delta",
                       "output_index": 0, "content_index": 0, "delta": ch})
        yield self._j({"type": "response.output_item.done", "output_index": 0, "item": {}})
        resp_obj["status"] = "completed"
        resp_obj["usage"] = {"input_tokens": 10, "output_tokens": len(text), "total_tokens": 10 + len(text)}
        yield self._j({"type": "response.completed", "response": resp_obj})

