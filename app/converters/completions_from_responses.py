"""Completions ← Responses 转换器：Completions 请求/响应 ↔ Responses 请求/响应"""

from __future__ import annotations

import json
import time
import uuid
from contextvars import ContextVar
from typing import Any

from app.core.config import get_settings
from app.core.converter import BaseConverter


class CompletionsFromResponsesConverter(BaseConverter):
    """Completions 请求 → Responses 请求，Responses 响应 → Completions 响应。"""

    _state_var: ContextVar[dict] = ContextVar("cfr_stream_state")

    @property
    def _stream_state(self) -> dict:
        try:
            return self._state_var.get()
        except LookupError:
            state: dict = {}
            self._state_var.set(state)
            return state

    # ── 请求转换 ───────────────────────────────────────────────

    def convert_request(self, request: dict) -> dict:
        """Completions 请求 dict → Responses 请求 dict"""
        input_items: list[dict] = []

        for msg in request["messages"]:
            role = msg["role"]
            content = msg.get("content")
            tool_calls = msg.get("tool_calls")
            tool_call_id = msg.get("tool_call_id")

            if role == "system":
                continue  # 在下面用 instructions 处理
            elif role == "user":
                text = content if isinstance(content, str) else "\n".join(
                    p.get("text", "") for p in (content or []) if p.get("type") == "text"
                )
                input_items.append({"type": "message", "role": "user", "content": text})
            elif role == "assistant":
                if tool_calls:
                    for tc in tool_calls:
                        input_items.append({
                            "type": "function_call",
                            "call_id": tc["id"],
                            "name": tc["function"]["name"],
                            "arguments": tc["function"]["arguments"],
                        })
                elif content:
                    text = content if isinstance(content, str) else "\n".join(
                        p.get("text", "") for p in content if p.get("type") == "text"
                    )
                    input_items.append({"type": "message", "role": "assistant", "content": text})
            elif role == "tool":
                input_items.append({
                    "type": "function_call_output",
                    "call_id": tool_call_id or "",
                    "output": content or "",
                })

        # system → instructions
        system_msgs = [m for m in request["messages"] if m["role"] == "system"]
        instructions = None
        if system_msgs:
            c = system_msgs[0].get("content", "")
            instructions = c if isinstance(c, str) else "\n".join(
                p.get("text", "") for p in (c or []) if p.get("type") == "text"
            )

        result: dict[str, Any] = {
            "model": request["model"],
            "input": input_items,
        }

        if instructions:
            result["instructions"] = instructions
        if request.get("max_tokens") is not None:
            result["max_output_tokens"] = request["max_tokens"]
        if request.get("temperature") is not None:
            result["temperature"] = request["temperature"]
        if request.get("top_p") is not None:
            result["top_p"] = request["top_p"]
        if request.get("tools"):
            result["tools"] = [_convert_tool_to_responses(t) for t in request["tools"]]
        if request.get("tool_choice") is not None:
            result["tool_choice"] = _convert_tool_choice_to_responses(request["tool_choice"])

        return result

    # ── 响应转换 ──────────────────────────────────────────────

    def convert_response(self, response: dict) -> dict:
        """Responses 响应 dict → Completions 响应 dict"""
        text_parts: list[str] = []
        tool_calls: list[dict] = []

        for item in response.get("output", []):
            if item["type"] == "message":
                for part in item.get("content", []):
                    if part.get("type") == "output_text":
                        text_parts.append(part.get("text", ""))
            elif item["type"] == "function_call":
                tool_calls.append({
                    "id": item.get("call_id", item.get("id", "")),
                    "type": "function",
                    "function": {
                        "name": item.get("name", ""),
                        "arguments": item.get("arguments", ""),
                    },
                })

        status = response.get("status", "completed")
        finish_reason = "length" if status == "incomplete" else ("tool_calls" if tool_calls else "stop")
        usage = response.get("usage", {})

        return {
            "id": f"chatcmpl-{response.get('id', '')}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": response.get("model", ""),
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "\n".join(text_parts) if text_parts else None,
                    **({"tool_calls": tool_calls} if tool_calls else {}),
                },
                "finish_reason": finish_reason,
            }],
            "usage": {
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
        }

    # ── 流式事件转换 ──────────────────────────────────────────

    def convert_stream_event(self, data: str) -> list[str]:
        """Responses SSE data → Completions SSE data list"""
        event = json.loads(data)
        state = self._stream_state
        event_type = event.get("type", "")
        results: list[str] = []

        if event_type == "response.created":
            resp = event.get("response", {})
            state["id"] = f"chatcmpl-{resp.get('id', '')}"
            state["model"] = resp.get("model", "")
            state["tool_call_index"] = -1
            results.append(_make_chunk_json(state, delta={"role": "assistant"}))

        elif event_type == "response.output_text.delta":
            results.append(_make_chunk_json(state, delta={"content": event.get("delta", "")}))

        elif event_type == "response.output_item.added":
            item = event.get("item", {})
            if item.get("type") == "function_call":
                state["tool_call_index"] = state.get("tool_call_index", -1) + 1
                results.append(_make_chunk_json(state, delta={
                    "tool_calls": [{
                        "index": state["tool_call_index"],
                        "id": item.get("call_id", ""),
                        "type": "function",
                        "function": {"name": item.get("name", ""), "arguments": ""},
                    }]
                }))

        elif event_type == "response.function_call_arguments.delta":
            results.append(_make_chunk_json(state, delta={
                "tool_calls": [{
                    "index": state.get("tool_call_index", 0),
                    "function": {"arguments": event.get("delta", "")},
                }]
            }))

        elif event_type == "response.completed":
            resp = event.get("response", {})
            status = resp.get("status", "completed")
            finish_reason = "length" if status == "incomplete" else "stop"
            if state.get("tool_call_index", -1) >= 0:
                finish_reason = "tool_calls"
            usage = resp.get("usage", {})
            results.append(_make_chunk_json(
                state, delta={}, finish_reason=finish_reason,
                usage={
                    "prompt_tokens": usage.get("input_tokens", 0),
                    "completion_tokens": usage.get("output_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                },
            ))
            results.append("[DONE]")

        return results


# ── 工具函数 ──────────────────────────────────────────────────


def _convert_tool_to_responses(tool: dict) -> dict:
    func = tool.get("function", {})
    return {
        "type": "function",
        "name": func.get("name", ""),
        "description": func.get("description", ""),
        "parameters": func.get("parameters", {}),
    }


def _convert_tool_choice_to_responses(choice: str | dict) -> str | dict:
    if isinstance(choice, str):
        return choice  # "auto" / "none" / "required"
    if isinstance(choice, dict):
        func = choice.get("function", {})
        return {"type": "function", "name": func.get("name", "")}
    return "auto"


def _make_chunk_json(
    state: dict,
    delta: dict,
    finish_reason: str | None = None,
    usage: dict | None = None,
) -> str:
    chunk = {
        "id": state.get("id", ""),
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": state.get("model", ""),
        "choices": [{
            "index": 0,
            "delta": delta,
            "finish_reason": finish_reason,
        }],
    }
    if usage:
        chunk["usage"] = usage
    return json.dumps(chunk, ensure_ascii=False)
