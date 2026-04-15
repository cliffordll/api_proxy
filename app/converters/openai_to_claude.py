"""OpenAI -> Claude 请求/响应/流式 转换器（纯逻辑，无 I/O）"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from openai.types.chat import (
    ChatCompletion,
    ChatCompletionChunk,
    ChatCompletionMessage,
)
from openai.types.chat.chat_completion import Choice
from openai.types.chat.chat_completion_chunk import (
    Choice as ChunkChoice,
    ChoiceDelta,
    ChoiceDeltaToolCall,
    ChoiceDeltaToolCallFunction,
)
from openai.types import CompletionUsage
from anthropic.types import Message, RawMessageStreamEvent

from app.core.config import get_settings, map_model
from app.core.converter import BaseConverter


class OpenAIToClaudeConverter(BaseConverter[dict, Message, RawMessageStreamEvent]):
    """OpenAI 格式请求 → Claude 格式请求，Claude 响应 → OpenAI 响应。"""

    # ── 请求转换 ───────────────────────────────────────────────

    def convert_request(self, openai_req: dict) -> dict:
        """OpenAI ChatCompletion 请求 dict -> Claude Messages 请求参数 dict"""
        settings = get_settings()

        system_text = None
        claude_messages: list[dict] = []

        for msg in openai_req["messages"]:
            role = msg["role"]
            content = msg.get("content")
            tool_calls = msg.get("tool_calls")
            tool_call_id = msg.get("tool_call_id")

            if role == "system":
                system_text = content if isinstance(content, str) else self._merge_text_parts(content)

            elif role == "user":
                claude_messages.append({
                    "role": "user",
                    "content": self._convert_content_to_claude(content),
                })

            elif role == "assistant":
                blocks: list[dict] = []
                if content:
                    text = content if isinstance(content, str) else self._merge_text_parts(content)
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
            result["tools"] = [self._convert_tool_def(t) for t in openai_req["tools"]]
        if openai_req.get("tool_choice") is not None:
            result["tool_choice"] = self._convert_tool_choice_to_claude(openai_req["tool_choice"])

        return result

    # ── 响应转换（非流式）──────────────────────────────────────

    def convert_response(self, claude_resp: Message) -> ChatCompletion:
        """anthropic.types.Message -> openai.types.chat.ChatCompletion"""
        text_parts: list[str] = []
        tool_calls_list = []

        for block in claude_resp.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                from openai.types.chat.chat_completion_message_tool_call import (
                    ChatCompletionMessageToolCall,
                    Function,
                )
                tool_calls_list.append(ChatCompletionMessageToolCall(
                    id=block.id,
                    type="function",
                    function=Function(
                        name=block.name,
                        arguments=json.dumps(block.input, ensure_ascii=False),
                    ),
                ))

        stop_reason_map = {
            "end_turn": "stop",
            "max_tokens": "length",
            "tool_use": "tool_calls",
        }

        usage = claude_resp.usage

        return ChatCompletion(
            id=f"chatcmpl-{claude_resp.id}",
            object="chat.completion",
            created=int(time.time()),
            model=claude_resp.model,
            choices=[Choice(
                index=0,
                message=ChatCompletionMessage(
                    role="assistant",
                    content="\n".join(text_parts) if text_parts else None,
                    tool_calls=tool_calls_list if tool_calls_list else None,
                ),
                finish_reason=stop_reason_map.get(claude_resp.stop_reason or "", "stop"),
            )],
            usage=CompletionUsage(
                prompt_tokens=usage.input_tokens,
                completion_tokens=usage.output_tokens,
                total_tokens=usage.input_tokens + usage.output_tokens,
            ),
        )

    # ── 流式事件转换 ──────────────────────────────────────────

    def convert_stream_event(self, event: RawMessageStreamEvent, state: dict) -> list[ChatCompletionChunk]:
        """anthropic RawMessageStreamEvent -> list[ChatCompletionChunk]"""
        event_type = event.type
        results: list[ChatCompletionChunk] = []

        if event_type == "message_start":
            msg = event.message
            state["id"] = f"chatcmpl-{msg.id}"
            state["model"] = msg.model
            state["tool_call_index"] = -1
            results.append(self._make_chunk(state, delta=ChoiceDelta(role="assistant")))

        elif event_type == "content_block_start":
            block = event.content_block
            if block.type == "tool_use":
                state["tool_call_index"] = state.get("tool_call_index", -1) + 1
                results.append(self._make_chunk(state, delta=ChoiceDelta(
                    tool_calls=[ChoiceDeltaToolCall(
                        index=state["tool_call_index"],
                        id=block.id,
                        type="function",
                        function=ChoiceDeltaToolCallFunction(name=block.name, arguments=""),
                    )]
                )))

        elif event_type == "content_block_delta":
            delta = event.delta
            if delta.type == "text_delta":
                results.append(self._make_chunk(state, delta=ChoiceDelta(content=delta.text)))
            elif delta.type == "input_json_delta":
                results.append(self._make_chunk(state, delta=ChoiceDelta(
                    tool_calls=[ChoiceDeltaToolCall(
                        index=state.get("tool_call_index", 0),
                        function=ChoiceDeltaToolCallFunction(arguments=delta.partial_json),
                    )]
                )))

        elif event_type == "message_delta":
            delta = event.delta
            stop_reason = getattr(delta, "stop_reason", "") or ""
            stop_map = {"end_turn": "stop", "max_tokens": "length", "tool_use": "tool_calls"}
            usage_obj = event.usage
            usage = None
            if usage_obj:
                output_tokens = getattr(usage_obj, "output_tokens", 0)
                usage = CompletionUsage(
                    prompt_tokens=0,
                    completion_tokens=output_tokens,
                    total_tokens=output_tokens,
                )
            results.append(self._make_chunk(
                state,
                delta=ChoiceDelta(),
                finish_reason=stop_map.get(stop_reason, "stop"),
                usage=usage,
            ))

        elif event_type == "message_stop":
            state["done"] = True

        return results

    # ── 私有方法 ──────────────────────────────────────────────

    @staticmethod
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

    @staticmethod
    def _merge_text_parts(content: list) -> str:
        return "\n".join(p.get("text", "") for p in content if p.get("type") == "text")

    @staticmethod
    def _convert_tool_def(tool: dict) -> dict:
        func = tool["function"]
        return {
            "name": func["name"],
            "description": func.get("description", ""),
            "input_schema": func.get("parameters", {}),
        }

    @staticmethod
    def _convert_tool_choice_to_claude(choice: str | dict) -> dict:
        if isinstance(choice, str):
            mapping = {"none": "none", "auto": "auto", "required": "any"}
            return {"type": mapping.get(choice, "auto")}
        return {"type": "tool", "name": choice["function"]["name"]}

    @staticmethod
    def _make_chunk(
        state: dict,
        delta: ChoiceDelta,
        finish_reason: str | None = None,
        usage: CompletionUsage | None = None,
    ) -> ChatCompletionChunk:
        return ChatCompletionChunk(
            id=state.get("id", ""),
            object="chat.completion.chunk",
            created=int(time.time()),
            model=state.get("model", ""),
            choices=[ChunkChoice(
                index=0,
                delta=delta,
                finish_reason=finish_reason,
            )],
            usage=usage,
        )
