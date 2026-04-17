"""Responses ← Completions 转换器：Responses 请求/响应 ↔ Completions 请求/响应"""

from __future__ import annotations

import json
import time
import uuid
from contextvars import ContextVar
from typing import Any

from openai.types.chat import ChatCompletion, ChatCompletionChunk

from app.core.config import get_settings
from app.core.converter import BaseConverter


class ResponsesFromCompletionsConverter(BaseConverter):
    """Responses 请求 → Completions 请求，Completions 响应 → Responses 响应。"""

    _state_var: ContextVar[dict] = ContextVar("rfc_stream_state")

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
        """Responses 请求 dict → Completions 请求 dict"""
        messages: list[dict] = []

        if request.get("instructions"):
            messages.append({"role": "system", "content": request["instructions"]})

        input_data = request.get("input", "")
        if isinstance(input_data, str):
            messages.append({"role": "user", "content": input_data})
        elif isinstance(input_data, list):
            for item in input_data:
                self._convert_input_item_to_completions(item, messages)

        result: dict[str, Any] = {
            "model": request["model"],
            "messages": messages,
        }

        if request.get("max_output_tokens") is not None:
            result["max_tokens"] = request["max_output_tokens"]
        if request.get("temperature") is not None:
            result["temperature"] = request["temperature"]
        if request.get("top_p") is not None:
            result["top_p"] = request["top_p"]
        if request.get("tools"):
            result["tools"] = [self._convert_tool_to_completions(t) for t in request["tools"]]
        if request.get("tool_choice") is not None:
            result["tool_choice"] = self._convert_tool_choice_to_completions(request["tool_choice"])

        return result

    # ── 响应转换 ──────────────────────────────────────────────

    def convert_response(self, response: ChatCompletion | dict) -> str:
        """Completions 响应 → Responses 响应 JSON 字符串"""
        response = self._to_dict(response)
        choice = response["choices"][0]
        message = choice["message"]
        output: list[dict] = []

        if message.get("content"):
            output.append({
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": message["content"]}],
            })

        if message.get("tool_calls"):
            for tc in message["tool_calls"]:
                output.append({
                    "type": "function_call",
                    "id": f"fc_{tc['id']}",
                    "call_id": tc["id"],
                    "name": tc["function"]["name"],
                    "arguments": tc["function"]["arguments"],
                })

        finish_reason = choice.get("finish_reason", "stop")
        status = "incomplete" if finish_reason == "length" else "completed"
        usage = response.get("usage", {})

        result = {
            "id": response.get("id", f"resp_{uuid.uuid4().hex[:24]}"),
            "object": "response",
            "created_at": int(time.time()),
            "model": response.get("model", ""),
            "output": output,
            "status": status,
            "usage": {
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
        }
        return json.dumps(result, ensure_ascii=False)

    # ── 流式事件转换 ──────────────────────────────────────────

    def convert_stream_event(self, event: ChatCompletionChunk | str) -> list[str]:
        """Completions SSE event → Responses SSE data list"""
        if isinstance(event, str) and event.strip() == "[DONE]":
            state = self._stream_state
            resp_obj = {
                "id": state.get("resp_id", ""),
                "object": "response",
                "created_at": int(time.time()),
                "model": state.get("model", ""),
                "status": state.get("status", "completed"),
                "output": [],
                "usage": {
                    "input_tokens": 0,
                    "output_tokens": state.get("output_tokens", 0),
                    "total_tokens": state.get("output_tokens", 0),
                },
            }
            return [self._resp_event("response.completed", {"response": resp_obj})]

        chunk = self._to_dict(event)
        state = self._stream_state
        results: list[str] = []

        choices = chunk.get("choices", [])
        choice = choices[0] if choices else None
        delta = choice.get("delta", {}) if choice else {}
        finish_reason = choice.get("finish_reason") if choice else None

        # 首个 chunk
        if not state.get("started"):
            state["started"] = True
            state["output_index"] = -1
            resp_id = chunk.get("id", f"resp_{uuid.uuid4().hex[:24]}")
            state["resp_id"] = resp_id
            state["model"] = chunk.get("model", "")
            resp_obj = {
                "id": resp_id, "object": "response",
                "created_at": int(time.time()),
                "model": state["model"], "status": "in_progress", "output": [],
            }
            results.append(self._resp_event("response.created", {"response": resp_obj}))
            results.append(self._resp_event("response.in_progress", {"response": resp_obj}))

            # 预创建 message output item
            state["output_index"] = 0
            item = {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": ""}]}
            results.append(self._resp_event("response.output_item.added", {"output_index": 0, "item": item}))

        # text content
        if delta.get("content"):
            results.append(self._resp_event("response.output_text.delta", {
                "output_index": 0, "content_index": 0,
                "delta": delta["content"],
            }))

        # tool_calls
        if delta.get("tool_calls"):
            for tc in delta["tool_calls"]:
                tc_index = tc.get("index", 0)
                if tc_index > state.get("current_tool_index", -1):
                    state["current_tool_index"] = tc_index
                    state["output_index"] = state.get("output_index", 0) + 1
                    item = {
                        "type": "function_call",
                        "id": f"fc_{tc.get('id', '')}",
                        "call_id": tc.get("id", ""),
                        "name": tc.get("function", {}).get("name", "") if tc.get("function") else "",
                        "arguments": "",
                    }
                    results.append(self._resp_event("response.output_item.added", {
                        "output_index": state["output_index"], "item": item,
                    }))

                func = tc.get("function", {})
                args = func.get("arguments", "") if func else ""
                if args:
                    results.append(self._resp_event("response.function_call_arguments.delta", {
                        "output_index": state["output_index"],
                        "delta": args,
                    }))

        if finish_reason:
            stop_map = {"stop": "completed", "length": "incomplete", "tool_calls": "completed"}
            state["status"] = stop_map.get(finish_reason, "completed")

        if chunk.get("usage"):
            state["output_tokens"] = chunk["usage"].get("completion_tokens", 0)

        return results

    # ── 工具方法 ──────────────────────────────────────────────

    @staticmethod
    def _convert_input_item_to_completions(item: dict, messages: list[dict]) -> None:
        item_type = item.get("type", "message")
        if item_type == "message":
            role = item.get("role", "user")
            content = item.get("content", "")
            if isinstance(content, str):
                messages.append({"role": role, "content": content})
            elif isinstance(content, list):
                text = "\n".join(
                    p.get("text", "") for p in content
                    if p.get("type") in ("input_text", "output_text", "text")
                )
                messages.append({"role": role, "content": text})
        elif item_type == "function_call":
            messages.append({
                "role": "assistant",
                "tool_calls": [{
                    "id": item.get("call_id", item.get("id", "")),
                    "type": "function",
                    "function": {
                        "name": item.get("name", ""),
                        "arguments": item.get("arguments", ""),
                    },
                }],
            })
        elif item_type == "function_call_output":
            messages.append({
                "role": "tool",
                "tool_call_id": item.get("call_id", ""),
                "content": item.get("output", ""),
            })

    @staticmethod
    def _convert_tool_to_completions(tool: dict) -> dict:
        return {
            "type": "function",
            "function": {
                "name": tool.get("name", ""),
                "description": tool.get("description", ""),
                "parameters": tool.get("parameters", {}),
            },
        }

    @staticmethod
    def _convert_tool_choice_to_completions(choice: str | dict) -> str | dict:
        if isinstance(choice, str):
            return choice  # "auto" / "required" / "none" 直接透传
        if isinstance(choice, dict) and choice.get("type") == "function":
            return {"type": "function", "function": {"name": choice.get("name", "")}}
        return "auto"

    @staticmethod
    def _resp_event(event_type: str, data: dict) -> str:
        """生成 Responses SSE 完整块（event + data + 空行）。"""
        payload = json.dumps({"type": event_type, **data}, ensure_ascii=False)
        return f"event: {event_type}\ndata: {payload}\n\n"
