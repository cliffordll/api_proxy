"""OpenAI -> Claude 请求/响应/流式 转换器（纯函数，无 I/O）"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from app.config import get_settings, map_model


# ── 请求转换 ───────────────────────────────────────────────

def convert_request(openai_req: dict) -> dict:
    """OpenAI ChatCompletion 请求 -> Claude Messages 请求"""
    settings = get_settings()

    system_text = None
    claude_messages: list[dict] = []

    for msg in openai_req["messages"]:
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
                    blocks.append({
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tc["function"]["name"],
                        "input": json.loads(tc["function"]["arguments"]) if isinstance(tc["function"]["arguments"], str) else tc["function"]["arguments"],
                    })
            claude_messages.append({"role": "assistant", "content": blocks or ""})

        elif role == "tool":
            # tool 结果 -> user message with tool_result block
            claude_messages.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": tool_call_id,
                    "content": content or "",
                }],
            })

    result: dict[str, Any] = {
        "model": map_model(openai_req["model"], "openai_to_claude"),
        "messages": claude_messages,
        "max_tokens": openai_req.get("max_tokens") or settings.default_max_tokens,
    }

    if system_text:
        result["system"] = system_text
    if openai_req.get("temperature") is not None:
        result["temperature"] = openai_req["temperature"]
    if openai_req.get("top_p") is not None:
        result["top_p"] = openai_req["top_p"]
    if openai_req.get("stop"):
        stop = openai_req["stop"]
        result["stop_sequences"] = [stop] if isinstance(stop, str) else stop
    if openai_req.get("stream"):
        result["stream"] = True
    if openai_req.get("tools"):
        result["tools"] = [_convert_tool_def(t) for t in openai_req["tools"]]
    if openai_req.get("tool_choice") is not None:
        result["tool_choice"] = _convert_tool_choice_to_claude(openai_req["tool_choice"])

    return result


def _convert_content_to_claude(content: str | list | None) -> str | list[dict]:
    if content is None:
        return ""
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    # list of content parts
    blocks: list[dict] = []
    for part in content:
        if part.get("type") == "text":
            blocks.append({"type": "text", "text": part["text"]})
        # 图片等暂跳过
    return blocks or ""


def _merge_text_parts(content: list) -> str:
    return "\n".join(p.get("text", "") for p in content if p.get("type") == "text")


def _convert_tool_def(tool: dict) -> dict:
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
    # {"type": "function", "function": {"name": "X"}}
    return {"type": "tool", "name": choice["function"]["name"]}


# ── 响应转换（非流式）──────────────────────────────────────

def convert_response(claude_resp: dict) -> dict:
    """Claude Messages 响应 -> OpenAI ChatCompletion 响应"""
    text_parts: list[str] = []
    tool_calls: list[dict] = []

    for block in claude_resp.get("content", []):
        if block["type"] == "text":
            text_parts.append(block["text"])
        elif block["type"] == "tool_use":
            tool_calls.append({
                "id": block["id"],
                "type": "function",
                "function": {
                    "name": block["name"],
                    "arguments": json.dumps(block["input"], ensure_ascii=False),
                },
            })

    message: dict[str, Any] = {
        "role": "assistant",
        "content": "\n".join(text_parts) if text_parts else None,
    }
    if tool_calls:
        message["tool_calls"] = tool_calls

    stop_reason_map = {
        "end_turn": "stop",
        "max_tokens": "length",
        "tool_use": "tool_calls",
    }

    usage = claude_resp.get("usage", {})

    return {
        "id": f"chatcmpl-{claude_resp.get('id', uuid.uuid4().hex[:24])}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": claude_resp.get("model", ""),
        "choices": [{
            "index": 0,
            "message": message,
            "finish_reason": stop_reason_map.get(claude_resp.get("stop_reason", ""), "stop"),
        }],
        "usage": {
            "prompt_tokens": usage.get("input_tokens", 0),
            "completion_tokens": usage.get("output_tokens", 0),
            "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
        },
    }


# ── 流式事件转换 ──────────────────────────────────────────

def convert_stream_event(event: dict, state: dict) -> list[str]:
    """
    Claude SSE 事件 -> OpenAI SSE data 行列表。
    state 用于跨事件维护: id, model, tool_call_index 等。
    返回空列表表示该事件不产生输出。
    """
    event_type = event.get("type", "")
    results: list[str] = []

    if event_type == "message_start":
        msg = event.get("message", {})
        state["id"] = f"chatcmpl-{msg.get('id', uuid.uuid4().hex[:24])}"
        state["model"] = msg.get("model", "")
        state["tool_call_index"] = -1
        chunk = _make_chunk(state, delta={"role": "assistant"})
        results.append(f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n")

    elif event_type == "content_block_start":
        block = event.get("content_block", {})
        if block.get("type") == "tool_use":
            state["tool_call_index"] = state.get("tool_call_index", -1) + 1
            chunk = _make_chunk(state, delta={
                "tool_calls": [{
                    "index": state["tool_call_index"],
                    "id": block["id"],
                    "type": "function",
                    "function": {"name": block["name"], "arguments": ""},
                }]
            })
            results.append(f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n")

    elif event_type == "content_block_delta":
        delta = event.get("delta", {})
        if delta.get("type") == "text_delta":
            chunk = _make_chunk(state, delta={"content": delta["text"]})
            results.append(f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n")
        elif delta.get("type") == "input_json_delta":
            chunk = _make_chunk(state, delta={
                "tool_calls": [{
                    "index": state.get("tool_call_index", 0),
                    "function": {"arguments": delta["partial_json"]},
                }]
            })
            results.append(f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n")

    elif event_type == "message_delta":
        delta = event.get("delta", {})
        stop_reason = delta.get("stop_reason", "")
        stop_map = {"end_turn": "stop", "max_tokens": "length", "tool_use": "tool_calls"}
        usage = event.get("usage", {})
        chunk = _make_chunk(
            state,
            delta={},
            finish_reason=stop_map.get(stop_reason, "stop"),
            usage={
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
                "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
            } if usage else None,
        )
        results.append(f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n")

    elif event_type == "message_stop":
        results.append("data: [DONE]\n\n")

    return results


def _make_chunk(state: dict, delta: dict, finish_reason: str | None = None, usage: dict | None = None) -> dict:
    chunk: dict[str, Any] = {
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
    return chunk
