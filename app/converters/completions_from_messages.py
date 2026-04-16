"""Completions ← Messages 转换器：Completions 请求/响应 ↔ Messages 请求/响应"""

from __future__ import annotations

import json
import time
from contextvars import ContextVar
from typing import Any

from app.core.config import get_settings, map_model
from app.core.converter import BaseConverter


class CompletionsFromMessagesConverter(BaseConverter):
    """Completions 请求 → Messages 请求，Messages 响应 → Completions 响应。

    全链路 dict/str，无 SDK 类型依赖。
    """

    _state_var: ContextVar[dict] = ContextVar("cfm_stream_state")

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
        """Completions 请求 dict → Messages 请求 dict"""
        settings = get_settings()

        system_text = None
        claude_messages: list[dict] = []

        for msg in request["messages"]:
            role = msg["role"]
            content = msg.get("content")
            tool_calls = msg.get("tool_calls")
            tool_call_id = msg.get("tool_call_id")

            if role == "system":
                system_text = content if isinstance(content, str) else _merge_text_parts(content)

            elif role == "user":
                claude_messages.append({
                    "role": "user",
                    "content": _convert_content_to_claude(content),
                })

            elif role == "assistant":
                blocks: list[dict] = []
                if content:
                    text = content if isinstance(content, str) else _merge_text_parts(content)
                    if text:
                        blocks.append({"type": "text", "text": text})
                if tool_calls:
                    for tc in tool_calls:
                        args = tc["function"]["arguments"]
                        blocks.append({
                            "type": "tool_use",
                            "id": tc["id"],
                            "name": tc["function"]["name"],
                            "input": json.loads(args) if isinstance(args, str) else args,
                        })
                claude_messages.append({"role": "assistant", "content": blocks or ""})

            elif role == "tool":
                claude_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": tool_call_id,
                        "content": content or "",
                    }],
                })

        result: dict[str, Any] = {
            "model": map_model(request["model"], "openai_to_claude"),
            "messages": claude_messages,
            "max_tokens": request.get("max_tokens") or settings["default_max_tokens"],
        }

        if system_text:
            result["system"] = system_text
        if request.get("temperature") is not None:
            result["temperature"] = request["temperature"]
        if request.get("top_p") is not None:
            result["top_p"] = request["top_p"]
        if request.get("stop"):
            stop = request["stop"]
            result["stop_sequences"] = [stop] if isinstance(stop, str) else stop
        if request.get("tools"):
            result["tools"] = [_convert_tool_to_claude(t) for t in request["tools"]]
        if request.get("tool_choice") is not None:
            result["tool_choice"] = _convert_tool_choice_to_claude(request["tool_choice"])

        return result

    # ── 响应转换（非流式）──────────────────────────────────────

    def convert_response(self, response: dict) -> dict:
        """Messages 响应 dict → Completions 响应 dict"""
        text_parts: list[str] = []
        tool_calls_list: list[dict] = []

        for block in response.get("content", []):
            if block["type"] == "text":
                text_parts.append(block["text"])
            elif block["type"] == "tool_use":
                tool_calls_list.append({
                    "id": block["id"],
                    "type": "function",
                    "function": {
                        "name": block["name"],
                        "arguments": json.dumps(block["input"], ensure_ascii=False),
                    },
                })

        stop_reason_map = {"end_turn": "stop", "max_tokens": "length", "tool_use": "tool_calls"}
        usage = response.get("usage", {})

        prompt_tokens = usage.get("input_tokens", 0)
        completion_tokens = usage.get("output_tokens", 0)

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
                    **({"tool_calls": tool_calls_list} if tool_calls_list else {}),
                },
                "finish_reason": stop_reason_map.get(response.get("stop_reason", ""), "stop"),
            }],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }

    # ── 流式事件转换 ──────────────────────────────────────────

    def convert_stream_event(self, data: str) -> list[str]:
        """Messages SSE data (JSON str) → Completions SSE data list[str]"""
        event = json.loads(data)
        state = self._stream_state
        event_type = event.get("type", "")
        results: list[str] = []

        if event_type == "message_start":
            msg = event.get("message", {})
            state["id"] = f"chatcmpl-{msg.get('id', '')}"
            state["model"] = msg.get("model", "")
            state["tool_call_index"] = -1
            results.append(_make_chunk_json(state, delta={"role": "assistant"}))

        elif event_type == "content_block_start":
            block = event.get("content_block", {})
            if block.get("type") == "tool_use":
                state["tool_call_index"] = state.get("tool_call_index", -1) + 1
                results.append(_make_chunk_json(state, delta={
                    "tool_calls": [{
                        "index": state["tool_call_index"],
                        "id": block.get("id", ""),
                        "type": "function",
                        "function": {"name": block.get("name", ""), "arguments": ""},
                    }]
                }))

        elif event_type == "content_block_delta":
            delta = event.get("delta", {})
            if delta.get("type") == "text_delta":
                results.append(_make_chunk_json(state, delta={"content": delta.get("text", "")}))
            elif delta.get("type") == "input_json_delta":
                results.append(_make_chunk_json(state, delta={
                    "tool_calls": [{
                        "index": state.get("tool_call_index", 0),
                        "function": {"arguments": delta.get("partial_json", "")},
                    }]
                }))

        elif event_type == "message_delta":
            delta = event.get("delta", {})
            stop_reason = delta.get("stop_reason", "")
            stop_map = {"end_turn": "stop", "max_tokens": "length", "tool_use": "tool_calls"}
            usage = event.get("usage", {})
            output_tokens = usage.get("output_tokens", 0)
            results.append(_make_chunk_json(
                state,
                delta={},
                finish_reason=stop_map.get(stop_reason, "stop"),
                usage={"prompt_tokens": 0, "completion_tokens": output_tokens, "total_tokens": output_tokens},
            ))

        elif event_type == "message_stop":
            results.append("[DONE]")

        return results


# ── 工具函数 ──────────────────────────────────────────────────


def _convert_content_to_claude(content: str | list | None) -> str | list[dict]:
    if content is None:
        return ""
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    blocks: list[dict] = []
    for part in content:
        if part.get("type") == "text":
            blocks.append({"type": "text", "text": part["text"]})
    return blocks or ""


def _merge_text_parts(content: list) -> str:
    return "\n".join(p.get("text", "") for p in content if p.get("type") == "text")


def _convert_tool_to_claude(tool: dict) -> dict:
    func = tool["function"]
    return {
        "name": func["name"],
        "description": func.get("description", ""),
        "input_schema": func.get("parameters", {}),
    }


def _convert_tool_choice_to_claude(choice: str | dict) -> dict:
    if isinstance(choice, str):
        mapping = {"none": "none", "auto": "auto", "required": "any"}
        return {"type": mapping.get(choice, "auto")}
    return {"type": "tool", "name": choice["function"]["name"]}


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
