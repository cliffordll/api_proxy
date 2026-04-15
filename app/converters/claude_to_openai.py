"""Claude -> OpenAI 请求/响应/流式 转换器（纯逻辑，无 I/O）"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from openai.types.chat import ChatCompletion, ChatCompletionChunk
from anthropic.types import Message, TextBlock, ToolUseBlock, Usage

from app.core.config import map_model
from app.core.converter import BaseConverter


class ClaudeToOpenAIConverter(BaseConverter[dict, ChatCompletion, ChatCompletionChunk]):
    """Claude 格式请求 → OpenAI 格式请求，OpenAI 响应 → Claude 响应。"""

    # ── 请求转换 ───────────────────────────────────────────────

    def convert_request(self, claude_req: dict) -> dict:
        """Claude Messages 请求 dict -> OpenAI ChatCompletion 请求参数 dict"""
        messages: list[dict] = []

        if claude_req.get("system"):
            messages.append({"role": "system", "content": claude_req["system"]})

        for msg in claude_req["messages"]:
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
                        tool_calls.append({
                            "id": block["id"],
                            "type": "function",
                            "function": {
                                "name": block["name"],
                                "arguments": json.dumps(block["input"], ensure_ascii=False) if isinstance(block["input"], dict) else block["input"],
                            },
                        })
                    elif btype == "tool_result":
                        tool_results.append(block)

                if tool_results:
                    for tr in tool_results:
                        tr_content = tr.get("content", "")
                        if isinstance(tr_content, list):
                            tr_content = "\n".join(b.get("text", "") for b in tr_content if b.get("type") == "text")
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
                    combined = "\n".join(text_parts) if text_parts else ""
                    messages.append({"role": role, "content": combined})

        result: dict[str, Any] = {
            "model": map_model(claude_req["model"], "claude_to_openai"),
            "messages": messages,
        }

        if claude_req.get("max_tokens") is not None:
            result["max_tokens"] = claude_req["max_tokens"]
        if claude_req.get("temperature") is not None:
            result["temperature"] = claude_req["temperature"]
        if claude_req.get("top_p") is not None:
            result["top_p"] = claude_req["top_p"]
        if claude_req.get("stop_sequences"):
            result["stop"] = claude_req["stop_sequences"]
        if claude_req.get("stream"):
            result["stream"] = True
        if claude_req.get("tools"):
            result["tools"] = [self._convert_tool_def(t) for t in claude_req["tools"]]
        if claude_req.get("tool_choice") is not None:
            result["tool_choice"] = self._convert_tool_choice_to_openai(claude_req["tool_choice"])

        return result

    # ── 响应转换（非流式）──────────────────────────────────────

    def convert_response(self, openai_resp: ChatCompletion) -> Message:
        """openai.types.chat.ChatCompletion -> anthropic.types.Message"""
        choice = openai_resp.choices[0]
        message = choice.message

        content_blocks: list[TextBlock | ToolUseBlock] = []

        if message.content:
            content_blocks.append(TextBlock(type="text", text=message.content))

        if message.tool_calls:
            for tc in message.tool_calls:
                content_blocks.append(ToolUseBlock(
                    type="tool_use",
                    id=tc.id,
                    name=tc.function.name,
                    input=json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else tc.function.arguments,
                ))

        finish_reason = choice.finish_reason or "stop"
        stop_reason_map = {
            "stop": "end_turn",
            "length": "max_tokens",
            "tool_calls": "tool_use",
        }

        usage = openai_resp.usage
        orig_id = openai_resp.id or ""
        claude_id = orig_id.replace("chatcmpl-", "msg_") if orig_id.startswith("chatcmpl-") else orig_id

        return Message(
            id=claude_id or f"msg_{uuid.uuid4().hex[:24]}",
            type="message",
            role="assistant",
            model=openai_resp.model,
            content=content_blocks,
            stop_reason=stop_reason_map.get(finish_reason, "end_turn"),
            usage=Usage(
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
            ),
        )

    # ── 流式事件转换 ──────────────────────────────────────────

    def convert_stream_event(self, chunk: ChatCompletionChunk, state: dict) -> list[str]:
        """
        openai.types.chat.ChatCompletionChunk -> Claude SSE event 行列表。
        Claude SSE 协议无对应 SDK 类型，仍返回 list[str]。
        """
        results: list[str] = []

        choices = chunk.choices or []
        choice = choices[0] if choices else None
        delta = choice.delta if choice else None
        finish_reason = choice.finish_reason if choice else None

        # 首个 chunk: 发 message_start + content_block_start
        if not state.get("started"):
            state["started"] = True
            state["content_block_index"] = 0
            state["content_block_open"] = True
            state["current_tool_index"] = -1
            msg_id = chunk.id or f"msg_{uuid.uuid4().hex[:24]}"
            if msg_id.startswith("chatcmpl-"):
                msg_id = "msg_" + msg_id[9:]
            state["msg_id"] = msg_id
            state["model"] = chunk.model or ""

            results.append(self._sse("message_start", {
                "message": {
                    "id": msg_id,
                    "type": "message",
                    "role": "assistant",
                    "model": state["model"],
                    "content": [],
                    "usage": {"input_tokens": 0, "output_tokens": 0},
                }
            }))
            results.append(self._sse("content_block_start", {
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            }))

        # text content
        if delta and delta.content:
            results.append(self._sse("content_block_delta", {
                "index": state.get("content_block_index", 0),
                "delta": {"type": "text_delta", "text": delta.content},
            }))

        # tool_calls
        if delta and delta.tool_calls:
            for tc in delta.tool_calls:
                tc_index = tc.index if tc.index is not None else 0

                if tc_index > state.get("current_tool_index", -1):
                    if state.get("content_block_open"):
                        results.append(self._sse("content_block_stop", {"index": state["content_block_index"]}))

                    state["content_block_index"] = state.get("content_block_index", 0) + 1
                    state["current_tool_index"] = tc_index
                    state["content_block_open"] = True

                    results.append(self._sse("content_block_start", {
                        "index": state["content_block_index"],
                        "content_block": {
                            "type": "tool_use",
                            "id": tc.id or "",
                            "name": tc.function.name if tc.function and tc.function.name else "",
                            "input": {},
                        },
                    }))

                args = tc.function.arguments if tc.function else None
                if args:
                    results.append(self._sse("content_block_delta", {
                        "index": state["content_block_index"],
                        "delta": {"type": "input_json_delta", "partial_json": args},
                    }))

        # finish_reason
        if finish_reason:
            stop_map = {"stop": "end_turn", "length": "max_tokens", "tool_calls": "tool_use"}
            state["stop_reason"] = stop_map.get(finish_reason, "end_turn")

        # usage
        if chunk.usage:
            state["output_tokens"] = chunk.usage.completion_tokens or 0

        return results

    def convert_stream_done(self, state: dict) -> list[str]:
        """生成流结束时的 Claude SSE 事件。"""
        results: list[str] = []

        if state.get("content_block_open"):
            results.append(self._sse("content_block_stop", {"index": state.get("content_block_index", 0)}))
            state["content_block_open"] = False

        results.append(self._sse("message_delta", {
            "delta": {"stop_reason": state.get("stop_reason", "end_turn")},
            "usage": {"output_tokens": state.get("output_tokens", 0)},
        }))
        results.append(self._sse("message_stop", {}))

        return results

    # ── 私有方法 ──────────────────────────────────────────────

    @staticmethod
    def _convert_tool_def(tool: dict) -> dict:
        return {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {}),
            },
        }

    @staticmethod
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

    @staticmethod
    def _sse(event_type: str, data: dict) -> str:
        payload = {"type": event_type, **data}
        return f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
