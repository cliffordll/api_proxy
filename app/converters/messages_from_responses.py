"""Messages ← Responses 转换器：Messages 请求/响应 ↔ Responses 请求/响应"""

from __future__ import annotations

import json
import uuid
from contextvars import ContextVar
from typing import Any

from openai.types.responses import Response, ResponseStreamEvent

from app.core.config import get_settings, map_model
from app.core.converter import BaseConverter


class MessagesFromResponsesConverter(BaseConverter):
    """Messages 请求 → Responses 请求，Responses 响应 → Messages 响应。"""

    _state_var: ContextVar[dict] = ContextVar("mfr_stream_state")

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
        """Messages 请求 dict → Responses 请求 dict"""
        input_items: list[dict] = []

        for msg in request["messages"]:
            role = msg["role"]
            content = msg.get("content")

            if isinstance(content, str):
                input_items.append({"type": "message", "role": role, "content": content})
                continue

            if isinstance(content, list):
                for block in content:
                    btype = block.get("type", "")
                    if btype == "text":
                        input_items.append({
                            "type": "message", "role": role,
                            "content": block["text"],
                        })
                    elif btype == "tool_use":
                        args = block["input"]
                        input_items.append({
                            "type": "function_call",
                            "call_id": block["id"],
                            "name": block["name"],
                            "arguments": json.dumps(args, ensure_ascii=False) if isinstance(args, dict) else args,
                        })
                    elif btype == "tool_result":
                        tr_content = block.get("content", "")
                        if isinstance(tr_content, list):
                            tr_content = "\n".join(
                                b.get("text", "") for b in tr_content if b.get("type") == "text"
                            )
                        input_items.append({
                            "type": "function_call_output",
                            "call_id": block.get("tool_use_id", ""),
                            "output": tr_content,
                        })

        result: dict[str, Any] = {
            "model": map_model(request["model"], "claude_to_openai"),
            "input": input_items,
        }

        if request.get("system"):
            result["instructions"] = request["system"]
        if request.get("max_tokens") is not None:
            result["max_output_tokens"] = request["max_tokens"]
        if request.get("temperature") is not None:
            result["temperature"] = request["temperature"]
        if request.get("top_p") is not None:
            result["top_p"] = request["top_p"]
        if request.get("tools"):
            result["tools"] = [self._convert_tool_to_responses(t) for t in request["tools"]]
        if request.get("tool_choice") is not None:
            result["tool_choice"] = self._convert_tool_choice_to_responses(request["tool_choice"])

        return result

    # ── 响应转换 ──────────────────────────────────────────────

    def convert_response(self, response: Response | dict) -> str:
        """Responses 响应 → Messages 响应 JSON 字符串"""
        response = self._to_dict(response)
        content_blocks: list[dict] = []

        for item in response.get("output", []):
            if item["type"] == "message":
                for part in item.get("content", []):
                    if part.get("type") == "output_text":
                        content_blocks.append({"type": "text", "text": part.get("text", "")})
            elif item["type"] == "function_call":
                args = item.get("arguments", "")
                content_blocks.append({
                    "type": "tool_use",
                    "id": item.get("call_id", item.get("id", "")),
                    "name": item.get("name", ""),
                    "input": json.loads(args) if isinstance(args, str) and args else {},
                })

        status = response.get("status", "completed")
        stop_reason = "max_tokens" if status == "incomplete" else "end_turn"
        if any(b["type"] == "tool_use" for b in content_blocks):
            stop_reason = "tool_use"

        usage = response.get("usage", {})
        resp_id = response.get("id", "")
        if not resp_id:
            resp_id = f"msg_{uuid.uuid4().hex[:24]}"

        result = {
            "id": resp_id,
            "type": "message",
            "role": "assistant",
            "model": response.get("model", ""),
            "content": content_blocks,
            "stop_reason": stop_reason,
            "usage": {
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
            },
        }
        return json.dumps(result, ensure_ascii=False)

    # ── 流式事件转换 ──────────────────────────────────────────

    def convert_stream_event(self, event: ResponseStreamEvent | str) -> list[str]:
        """Responses SSE event → Messages SSE data list"""
        event = self._to_dict(event)
        state = self._stream_state
        event_type = event.get("type", "")
        results: list[str] = []

        if event_type == "response.created":
            resp = event.get("response", {})
            msg_id = resp.get("id", f"msg_{uuid.uuid4().hex[:24]}")
            state["msg_id"] = msg_id
            state["model"] = resp.get("model", "")
            state["content_block_index"] = 0
            state["content_block_open"] = True
            state["current_tool_index"] = -1

            results.append(self._event_json("message_start", {
                "message": {
                    "id": msg_id, "type": "message", "role": "assistant",
                    "model": state["model"], "content": [],
                    "usage": {"input_tokens": 0, "output_tokens": 0},
                }
            }))
            results.append(self._event_json("content_block_start", {
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            }))

        elif event_type == "response.output_text.delta":
            results.append(self._event_json("content_block_delta", {
                "index": state.get("content_block_index", 0),
                "delta": {"type": "text_delta", "text": event.get("delta", "")},
            }))

        elif event_type == "response.output_item.added":
            item = event.get("item", {})
            if item.get("type") == "function_call":
                # 关闭当前 block
                if state.get("content_block_open"):
                    results.append(self._event_json("content_block_stop", {
                        "index": state["content_block_index"],
                    }))

                state["content_block_index"] = state.get("content_block_index", 0) + 1
                state["content_block_open"] = True
                state["current_tool_index"] = state.get("current_tool_index", -1) + 1

                results.append(self._event_json("content_block_start", {
                    "index": state["content_block_index"],
                    "content_block": {
                        "type": "tool_use",
                        "id": item.get("call_id", item.get("id", "")),
                        "name": item.get("name", ""),
                        "input": {},
                    },
                }))

        elif event_type == "response.function_call_arguments.delta":
            results.append(self._event_json("content_block_delta", {
                "index": state.get("content_block_index", 0),
                "delta": {"type": "input_json_delta", "partial_json": event.get("delta", "")},
            }))

        elif event_type == "response.completed":
            resp = event.get("response", {})
            status = resp.get("status", "completed")
            stop_reason = "max_tokens" if status == "incomplete" else "end_turn"
            if state.get("current_tool_index", -1) >= 0:
                stop_reason = "tool_use"
            usage = resp.get("usage", {})
            state["stop_reason"] = stop_reason
            state["output_tokens"] = usage.get("output_tokens", 0)

        return results

    def convert_stream_done(self) -> list[str]:
        """流结束 → Messages 结束事件列表"""
        state = self._stream_state
        results: list[str] = []

        if state.get("content_block_open"):
            results.append(self._event_json("content_block_stop", {
                "index": state.get("content_block_index", 0),
            }))
            state["content_block_open"] = False

        results.append(self._event_json("message_delta", {
            "delta": {"stop_reason": state.get("stop_reason", "end_turn")},
            "usage": {"output_tokens": state.get("output_tokens", 0)},
        }))
        results.append(self._event_json("message_stop", {}))

        return results

    # ── 工具方法 ──────────────────────────────────────────────

    @staticmethod
    def _convert_tool_to_responses(tool: dict) -> dict:
        return {
            "type": "function",
            "name": tool.get("name", ""),
            "description": tool.get("description", ""),
            "parameters": tool.get("input_schema", {}),
        }

    @staticmethod
    def _convert_tool_choice_to_responses(choice: dict) -> str | dict:
        ctype = choice.get("type", "auto")
        if ctype == "none":
            return "none"
        if ctype == "auto":
            return "auto"
        if ctype == "any":
            return "required"
        if ctype == "tool":
            return {"type": "function", "name": choice.get("name", "")}
        return "auto"

    @staticmethod
    def _event_json(event_type: str, data: dict) -> str:
        """生成 Messages SSE 完整块（event + data + 空行）。"""
        payload = {"type": event_type, **data}
        return f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
