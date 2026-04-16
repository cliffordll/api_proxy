"""Messages ← Completions 转换器：Messages 请求/响应 ↔ Completions 请求/响应"""

from __future__ import annotations

import json
import uuid
from contextvars import ContextVar
from typing import Any

from app.core.config import map_model
from app.core.converter import BaseConverter


class MessagesFromCompletionsConverter(BaseConverter):
    """Messages 请求 → Completions 请求，Completions 响应 → Messages 响应。

    全链路 dict/str，无 SDK 类型依赖。
    """

    _state_var: ContextVar[dict] = ContextVar("mfc_stream_state")

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
        """Messages 请求 dict → Completions 请求 dict"""
        messages: list[dict] = []

        if request.get("system"):
            messages.append({"role": "system", "content": request["system"]})

        for msg in request["messages"]:
            role = msg["role"]
            content = msg.get("content")

            if isinstance(content, str):
                messages.append({"role": role, "content": content})
                continue

            if isinstance(content, list):
                text_parts: list[str] = []
                tool_calls: list[dict] = []
                tool_results: list[dict] = []

                for block in content:
                    btype = block.get("type", "")
                    if btype == "text":
                        text_parts.append(block["text"])
                    elif btype == "tool_use":
                        args = block["input"]
                        tool_calls.append({
                            "id": block["id"],
                            "type": "function",
                            "function": {
                                "name": block["name"],
                                "arguments": json.dumps(args, ensure_ascii=False) if isinstance(args, dict) else args,
                            },
                        })
                    elif btype == "tool_result":
                        tool_results.append(block)

                if tool_results:
                    for tr in tool_results:
                        tr_content = tr.get("content", "")
                        if isinstance(tr_content, list):
                            tr_content = "\n".join(
                                b.get("text", "") for b in tr_content if b.get("type") == "text"
                            )
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tr["tool_use_id"],
                            "content": tr_content,
                        })
                elif tool_calls:
                    msg_dict: dict[str, Any] = {"role": "assistant"}
                    if text_parts:
                        msg_dict["content"] = "\n".join(text_parts)
                    msg_dict["tool_calls"] = tool_calls
                    messages.append(msg_dict)
                else:
                    messages.append({"role": role, "content": "\n".join(text_parts) if text_parts else ""})

        result: dict[str, Any] = {
            "model": map_model(request["model"], "claude_to_openai"),
            "messages": messages,
        }

        if request.get("max_tokens") is not None:
            result["max_tokens"] = request["max_tokens"]
        if request.get("temperature") is not None:
            result["temperature"] = request["temperature"]
        if request.get("top_p") is not None:
            result["top_p"] = request["top_p"]
        if request.get("stop_sequences"):
            result["stop"] = request["stop_sequences"]
        if request.get("tools"):
            result["tools"] = [_convert_tool_to_openai(t) for t in request["tools"]]
        if request.get("tool_choice") is not None:
            result["tool_choice"] = _convert_tool_choice_to_openai(request["tool_choice"])

        return result

    # ── 响应转换（非流式）──────────────────────────────────────

    def convert_response(self, response: dict) -> dict:
        """Completions 响应 dict → Messages 响应 dict"""
        choice = response["choices"][0]
        message = choice["message"]

        content_blocks: list[dict] = []

        if message.get("content"):
            content_blocks.append({"type": "text", "text": message["content"]})

        if message.get("tool_calls"):
            for tc in message["tool_calls"]:
                args = tc["function"]["arguments"]
                content_blocks.append({
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": tc["function"]["name"],
                    "input": json.loads(args) if isinstance(args, str) else args,
                })

        finish_reason = choice.get("finish_reason", "stop")
        stop_reason_map = {"stop": "end_turn", "length": "max_tokens", "tool_calls": "tool_use"}

        usage = response.get("usage", {})
        orig_id = response.get("id", "")
        msg_id = orig_id.replace("chatcmpl-", "msg_") if orig_id.startswith("chatcmpl-") else orig_id
        if not msg_id:
            msg_id = f"msg_{uuid.uuid4().hex[:24]}"

        return {
            "id": msg_id,
            "type": "message",
            "role": "assistant",
            "model": response.get("model", ""),
            "content": content_blocks,
            "stop_reason": stop_reason_map.get(finish_reason, "end_turn"),
            "usage": {
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
            },
        }

    # ── 流式事件转换 ──────────────────────────────────────────

    def convert_stream_event(self, data: str) -> list[str]:
        """Completions SSE data (JSON str) → Messages SSE data list[str]"""
        if data == "[DONE]":
            return []

        chunk = json.loads(data)
        state = self._stream_state
        results: list[str] = []

        choices = chunk.get("choices", [])
        choice = choices[0] if choices else None
        delta = choice.get("delta", {}) if choice else {}
        finish_reason = choice.get("finish_reason") if choice else None

        # 首个 chunk: message_start + content_block_start
        if not state.get("started"):
            state["started"] = True
            state["content_block_index"] = 0
            state["content_block_open"] = True
            state["current_tool_index"] = -1

            msg_id = chunk.get("id", "")
            if msg_id.startswith("chatcmpl-"):
                msg_id = "msg_" + msg_id[9:]
            elif not msg_id:
                msg_id = f"msg_{uuid.uuid4().hex[:24]}"
            state["msg_id"] = msg_id
            state["model"] = chunk.get("model", "")

            results.append(_event_json("message_start", {
                "message": {
                    "id": msg_id,
                    "type": "message",
                    "role": "assistant",
                    "model": state["model"],
                    "content": [],
                    "usage": {"input_tokens": 0, "output_tokens": 0},
                }
            }))
            results.append(_event_json("content_block_start", {
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            }))

        # text content
        if delta.get("content"):
            results.append(_event_json("content_block_delta", {
                "index": state.get("content_block_index", 0),
                "delta": {"type": "text_delta", "text": delta["content"]},
            }))

        # tool_calls
        if delta.get("tool_calls"):
            for tc in delta["tool_calls"]:
                tc_index = tc.get("index", 0)

                if tc_index > state.get("current_tool_index", -1):
                    if state.get("content_block_open"):
                        results.append(_event_json("content_block_stop", {
                            "index": state["content_block_index"],
                        }))

                    state["content_block_index"] = state.get("content_block_index", 0) + 1
                    state["current_tool_index"] = tc_index
                    state["content_block_open"] = True

                    results.append(_event_json("content_block_start", {
                        "index": state["content_block_index"],
                        "content_block": {
                            "type": "tool_use",
                            "id": tc.get("id", ""),
                            "name": tc.get("function", {}).get("name", "") if tc.get("function") else "",
                            "input": {},
                        },
                    }))

                func = tc.get("function", {})
                args = func.get("arguments", "") if func else ""
                if args:
                    results.append(_event_json("content_block_delta", {
                        "index": state["content_block_index"],
                        "delta": {"type": "input_json_delta", "partial_json": args},
                    }))

        # finish_reason
        if finish_reason:
            stop_map = {"stop": "end_turn", "length": "max_tokens", "tool_calls": "tool_use"}
            state["stop_reason"] = stop_map.get(finish_reason, "end_turn")

        # usage
        if chunk.get("usage"):
            state["output_tokens"] = chunk["usage"].get("completion_tokens", 0)

        return results

    def convert_stream_done(self) -> list[str]:
        """流结束 → Messages 结束事件列表"""
        state = self._stream_state
        results: list[str] = []

        if state.get("content_block_open"):
            results.append(_event_json("content_block_stop", {
                "index": state.get("content_block_index", 0),
            }))
            state["content_block_open"] = False

        results.append(_event_json("message_delta", {
            "delta": {"stop_reason": state.get("stop_reason", "end_turn")},
            "usage": {"output_tokens": state.get("output_tokens", 0)},
        }))
        results.append(_event_json("message_stop", {}))

        return results


# ── 工具函数 ──────────────────────────────────────────────────


def _convert_tool_to_openai(tool: dict) -> dict:
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": tool.get("input_schema", {}),
        },
    }


def _convert_tool_choice_to_openai(choice: dict) -> str | dict:
    ctype = choice.get("type", "auto")
    if ctype == "none":
        return "none"
    if ctype == "auto":
        return "auto"
    if ctype == "any":
        return "required"
    if ctype == "tool":
        return {"type": "function", "function": {"name": choice["name"]}}
    return "auto"


def _event_json(event_type: str, data: dict) -> str:
    """生成 Messages SSE data JSON 字符串（含 type 字段）。"""
    payload = {"type": event_type, **data}
    return json.dumps(payload, ensure_ascii=False)
