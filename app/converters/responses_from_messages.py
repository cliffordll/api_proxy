"""Responses ← Messages 转换器：Responses 请求/响应 ↔ Messages 请求/响应"""

from __future__ import annotations

import json
import time
import uuid
from contextvars import ContextVar

from anthropic.types import Message, RawMessageStreamEvent

from app.core.config import get_settings, map_model
from app.core.converter import BaseConverter


class ResponsesFromMessagesConverter(BaseConverter):
    """Responses 请求 → Messages 请求，Messages 响应 → Responses 响应。"""

    _state_var: ContextVar[dict] = ContextVar("rfm_stream_state")

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
        """Responses 请求 dict → Messages 请求 dict"""
        settings = get_settings()
        claude_messages: list[dict] = []

        input_data = request.get("input", "")
        if isinstance(input_data, str):
            claude_messages.append({
                "role": "user",
                "content": [{"type": "text", "text": input_data}],
            })
        elif isinstance(input_data, list):
            for item in input_data:
                _convert_responses_input_item(item, claude_messages)

        result: dict[str, Any] = {
            "model": map_model(request["model"], "openai_to_claude"),
            "messages": claude_messages,
            "max_tokens": request.get("max_output_tokens") or settings["default_max_tokens"],
        }

        if request.get("instructions"):
            result["system"] = request["instructions"]
        if request.get("temperature") is not None:
            result["temperature"] = request["temperature"]
        if request.get("top_p") is not None:
            result["top_p"] = request["top_p"]
        if request.get("tools"):
            result["tools"] = [_convert_tool_to_claude(t) for t in request["tools"]]
        if request.get("tool_choice") is not None:
            result["tool_choice"] = _convert_tool_choice_to_claude(request["tool_choice"])

        return result

    # ── 响应转换 ──────────────────────────────────────────────

    def convert_response(self, response: Message | dict) -> str:
        """Messages 响应 → Responses 响应 JSON 字符串"""
        response = self._to_dict(response)
        output: list[dict] = []
        text_parts: list[str] = []

        for block in response.get("content", []):
            if block["type"] == "text":
                text_parts.append(block["text"])
            elif block["type"] == "tool_use":
                # 先把累积的文本输出
                if text_parts:
                    output.append(_make_message_output(text_parts))
                    text_parts = []
                output.append({
                    "type": "function_call",
                    "id": f"fc_{block['id']}",
                    "call_id": block["id"],
                    "name": block["name"],
                    "arguments": json.dumps(block["input"], ensure_ascii=False),
                })

        if text_parts:
            output.append(_make_message_output(text_parts))

        stop_reason = response.get("stop_reason", "end_turn")
        status = "incomplete" if stop_reason == "max_tokens" else "completed"
        usage = response.get("usage", {})

        result = {
            "id": response.get("id", f"resp_{uuid.uuid4().hex[:24]}"),
            "object": "response",
            "created_at": int(time.time()),
            "model": response.get("model", ""),
            "output": output,
            "status": status,
            "usage": {
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
            },
        }
        return json.dumps(result, ensure_ascii=False)

    # ── 流式事件转换 ──────────────────────────────────────────

    def convert_stream_event(self, event: RawMessageStreamEvent | str) -> list[str]:
        """Messages SSE event → Responses SSE data list"""
        event = self._to_dict(event)
        state = self._stream_state
        event_type = event.get("type", "")
        results: list[str] = []

        if event_type == "message_start":
            msg = event.get("message", {})
            resp_id = msg.get("id", f"resp_{uuid.uuid4().hex[:24]}")
            state["resp_id"] = resp_id
            state["model"] = msg.get("model", "")
            state["output_index"] = -1
            state["content_index"] = 0
            resp_obj = _make_response_obj(resp_id, state["model"], "in_progress")
            results.append(_resp_event("response.created", {"response": resp_obj}))
            results.append(_resp_event("response.in_progress", {"response": resp_obj}))

        elif event_type == "content_block_start":
            block = event.get("content_block", {})
            state["output_index"] = state.get("output_index", -1) + 1
            idx = state["output_index"]

            if block.get("type") == "text":
                item = {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": ""}]}
                results.append(_resp_event("response.output_item.added", {"output_index": idx, "item": item}))
                results.append(_resp_event("response.content_part.added", {
                    "output_index": idx, "content_index": 0,
                    "part": {"type": "output_text", "text": ""},
                }))
            elif block.get("type") == "tool_use":
                state["current_tool_id"] = block.get("id", "")
                state["current_tool_name"] = block.get("name", "")
                item = {
                    "type": "function_call",
                    "id": f"fc_{block.get('id', '')}",
                    "call_id": block.get("id", ""),
                    "name": block.get("name", ""),
                    "arguments": "",
                }
                results.append(_resp_event("response.output_item.added", {"output_index": idx, "item": item}))

        elif event_type == "content_block_delta":
            delta = event.get("delta", {})
            idx = state.get("output_index", 0)

            if delta.get("type") == "text_delta":
                results.append(_resp_event("response.output_text.delta", {
                    "output_index": idx, "content_index": 0,
                    "delta": delta.get("text", ""),
                }))
            elif delta.get("type") == "input_json_delta":
                results.append(_resp_event("response.function_call_arguments.delta", {
                    "output_index": idx,
                    "delta": delta.get("partial_json", ""),
                }))

        elif event_type == "content_block_stop":
            idx = state.get("output_index", 0)
            results.append(_resp_event("response.output_item.done", {"output_index": idx, "item": {}}))

        elif event_type == "message_delta":
            delta = event.get("delta", {})
            stop_reason = delta.get("stop_reason", "end_turn")
            status = "incomplete" if stop_reason == "max_tokens" else "completed"
            usage = event.get("usage", {})
            state["status"] = status
            state["output_tokens"] = usage.get("output_tokens", 0)

        elif event_type == "message_stop":
            resp_obj = _make_response_obj(
                state.get("resp_id", ""), state.get("model", ""),
                state.get("status", "completed"),
            )
            resp_obj["usage"] = {
                "input_tokens": 0,
                "output_tokens": state.get("output_tokens", 0),
                "total_tokens": state.get("output_tokens", 0),
            }
            results.append(_resp_event("response.completed", {"response": resp_obj}))

        return results


# ── 工具函数 ──────────────────────────────────────────────────


def _convert_responses_input_item(item: dict, messages: list[dict]) -> None:
    """将 Responses input 数组中的单个 item 转换为 Messages 消息。"""
    item_type = item.get("type", "message")

    if item_type == "message":
        role = item.get("role", "user")
        content = item.get("content", "")
        if isinstance(content, str):
            messages.append({"role": role, "content": [{"type": "text", "text": content}]})
        elif isinstance(content, list):
            blocks: list[dict] = []
            for part in content:
                ptype = part.get("type", "")
                if ptype in ("input_text", "output_text", "text"):
                    blocks.append({"type": "text", "text": part.get("text", "")})
            if blocks:
                messages.append({"role": role, "content": blocks})

    elif item_type == "function_call":
        args = item.get("arguments", "")
        messages.append({
            "role": "assistant",
            "content": [{
                "type": "tool_use",
                "id": item.get("call_id", item.get("id", "")),
                "name": item.get("name", ""),
                "input": json.loads(args) if isinstance(args, str) and args else {},
            }],
        })

    elif item_type == "function_call_output":
        messages.append({
            "role": "user",
            "content": [{
                "type": "tool_result",
                "tool_use_id": item.get("call_id", ""),
                "content": item.get("output", ""),
            }],
        })


def _convert_tool_to_claude(tool: dict) -> dict:
    return {
        "name": tool.get("name", ""),
        "description": tool.get("description", ""),
        "input_schema": tool.get("parameters", {}),
    }


def _convert_tool_choice_to_claude(choice: str | dict) -> dict:
    if isinstance(choice, str):
        mapping = {"auto": "auto", "required": "any", "none": "none"}
        return {"type": mapping.get(choice, "auto")}
    if isinstance(choice, dict) and choice.get("type") == "function":
        return {"type": "tool", "name": choice.get("name", "")}
    return {"type": "auto"}


def _make_message_output(text_parts: list[str]) -> dict:
    return {
        "type": "message",
        "role": "assistant",
        "content": [{"type": "output_text", "text": "\n".join(text_parts)}],
    }


def _make_response_obj(resp_id: str, model: str, status: str) -> dict:
    return {
        "id": resp_id,
        "object": "response",
        "created_at": int(time.time()),
        "model": model,
        "status": status,
        "output": [],
    }


def _resp_event(event_type: str, data: dict) -> str:
    """生成 Responses SSE 完整块（event + data + 空行）。"""
    payload = json.dumps({"type": event_type, **data}, ensure_ascii=False)
    return f"event: {event_type}\ndata: {payload}\n\n"
