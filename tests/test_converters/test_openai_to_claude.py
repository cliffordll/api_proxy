"""openai_to_claude 转换器单元测试"""

import json
import pytest
from app.converters.openai_to_claude import convert_request, convert_response, convert_stream_event


# ── convert_request ────────────────────────────────────────

class TestConvertRequest:
    def test_simple_text(self):
        req = {
            "model": "gpt-4o",
            "messages": [
                {"role": "user", "content": "Hello"}
            ],
        }
        result = convert_request(req)
        assert result["model"] == "claude-sonnet-4-6-20250514"
        assert result["messages"][0]["role"] == "user"
        assert result["messages"][0]["content"] == [{"type": "text", "text": "Hello"}]
        assert result["max_tokens"] == 4096  # 默认值

    def test_system_message_extracted(self):
        req = {
            "model": "gpt-4",
            "messages": [
                {"role": "system", "content": "You are helpful"},
                {"role": "user", "content": "Hi"},
            ],
        }
        result = convert_request(req)
        assert result["system"] == "You are helpful"
        assert len(result["messages"]) == 1
        assert result["messages"][0]["role"] == "user"

    def test_max_tokens_passthrough(self):
        req = {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 1000,
        }
        result = convert_request(req)
        assert result["max_tokens"] == 1000

    def test_optional_params(self):
        req = {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Hi"}],
            "temperature": 0.7,
            "top_p": 0.9,
            "stop": ["END"],
            "stream": True,
        }
        result = convert_request(req)
        assert result["temperature"] == 0.7
        assert result["top_p"] == 0.9
        assert result["stop_sequences"] == ["END"]
        assert result["stream"] is True

    def test_stop_string_to_list(self):
        req = {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Hi"}],
            "stop": "STOP",
        }
        result = convert_request(req)
        assert result["stop_sequences"] == ["STOP"]

    def test_tools_conversion(self):
        req = {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Hi"}],
            "tools": [{
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get weather",
                    "parameters": {"type": "object", "properties": {"city": {"type": "string"}}},
                },
            }],
        }
        result = convert_request(req)
        assert result["tools"][0]["name"] == "get_weather"
        assert result["tools"][0]["input_schema"]["type"] == "object"

    def test_tool_choice_auto(self):
        req = {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Hi"}],
            "tools": [{"type": "function", "function": {"name": "f", "parameters": {}}}],
            "tool_choice": "auto",
        }
        result = convert_request(req)
        assert result["tool_choice"] == {"type": "auto"}

    def test_tool_choice_required(self):
        req = {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Hi"}],
            "tools": [{"type": "function", "function": {"name": "f", "parameters": {}}}],
            "tool_choice": "required",
        }
        result = convert_request(req)
        assert result["tool_choice"] == {"type": "any"}

    def test_tool_choice_specific(self):
        req = {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Hi"}],
            "tools": [{"type": "function", "function": {"name": "get_weather", "parameters": {}}}],
            "tool_choice": {"type": "function", "function": {"name": "get_weather"}},
        }
        result = convert_request(req)
        assert result["tool_choice"] == {"type": "tool", "name": "get_weather"}

    def test_assistant_with_tool_calls(self):
        req = {
            "model": "gpt-4o",
            "messages": [
                {"role": "user", "content": "What's the weather?"},
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "call_123",
                        "type": "function",
                        "function": {"name": "get_weather", "arguments": '{"city":"Beijing"}'},
                    }],
                },
                {"role": "tool", "tool_call_id": "call_123", "content": "Sunny 25°C"},
            ],
        }
        result = convert_request(req)
        # assistant message with tool_use block
        assistant_msg = result["messages"][1]
        assert assistant_msg["role"] == "assistant"
        assert assistant_msg["content"][0]["type"] == "tool_use"
        assert assistant_msg["content"][0]["input"] == {"city": "Beijing"}
        # tool result -> user message with tool_result block
        tool_msg = result["messages"][2]
        assert tool_msg["role"] == "user"
        assert tool_msg["content"][0]["type"] == "tool_result"
        assert tool_msg["content"][0]["tool_use_id"] == "call_123"

    def test_model_passthrough(self):
        req = {
            "model": "unknown-model",
            "messages": [{"role": "user", "content": "Hi"}],
        }
        result = convert_request(req)
        assert result["model"] == "unknown-model"

    def test_multi_turn(self):
        req = {
            "model": "gpt-4o",
            "messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
                {"role": "user", "content": "How are you?"},
            ],
        }
        result = convert_request(req)
        assert len(result["messages"]) == 3
        assert result["messages"][0]["role"] == "user"
        assert result["messages"][1]["role"] == "assistant"
        assert result["messages"][2]["role"] == "user"


# ── convert_response ──────────────────────────────────────

class TestConvertResponse:
    def test_text_response(self):
        resp = {
            "id": "msg_abc",
            "model": "claude-sonnet-4-6-20250514",
            "content": [{"type": "text", "text": "Hello!"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        result = convert_response(resp)
        assert result["id"].startswith("chatcmpl-")
        assert result["choices"][0]["message"]["content"] == "Hello!"
        assert result["choices"][0]["finish_reason"] == "stop"
        assert result["usage"]["prompt_tokens"] == 10
        assert result["usage"]["completion_tokens"] == 5
        assert result["usage"]["total_tokens"] == 15

    def test_tool_use_response(self):
        resp = {
            "id": "msg_abc",
            "model": "claude-sonnet-4-6-20250514",
            "content": [
                {"type": "text", "text": "Let me check."},
                {"type": "tool_use", "id": "tu_1", "name": "get_weather", "input": {"city": "Beijing"}},
            ],
            "stop_reason": "tool_use",
            "usage": {"input_tokens": 20, "output_tokens": 10},
        }
        result = convert_response(resp)
        assert result["choices"][0]["finish_reason"] == "tool_calls"
        tc = result["choices"][0]["message"]["tool_calls"][0]
        assert tc["function"]["name"] == "get_weather"
        assert json.loads(tc["function"]["arguments"]) == {"city": "Beijing"}

    def test_max_tokens_stop(self):
        resp = {
            "id": "msg_abc",
            "model": "claude-sonnet-4-6-20250514",
            "content": [{"type": "text", "text": "partial"}],
            "stop_reason": "max_tokens",
            "usage": {"input_tokens": 5, "output_tokens": 100},
        }
        result = convert_response(resp)
        assert result["choices"][0]["finish_reason"] == "length"


# ── convert_stream_event ──────────────────────────────────

class TestConvertStreamEvent:
    def test_message_start(self):
        state = {}
        event = {
            "type": "message_start",
            "message": {"id": "msg_001", "model": "claude-sonnet-4-6-20250514"},
        }
        results = convert_stream_event(event, state)
        assert len(results) == 1
        chunk = json.loads(results[0].replace("data: ", ""))
        assert chunk["choices"][0]["delta"]["role"] == "assistant"

    def test_text_delta(self):
        state = {"id": "chatcmpl-001", "model": "m"}
        event = {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": "Hello"},
        }
        results = convert_stream_event(event, state)
        assert len(results) == 1
        chunk = json.loads(results[0].replace("data: ", ""))
        assert chunk["choices"][0]["delta"]["content"] == "Hello"

    def test_tool_use_stream(self):
        state = {"id": "chatcmpl-001", "model": "m", "tool_call_index": -1}
        # content_block_start for tool_use
        event = {
            "type": "content_block_start",
            "index": 1,
            "content_block": {"type": "tool_use", "id": "tu_1", "name": "get_weather"},
        }
        results = convert_stream_event(event, state)
        assert len(results) == 1
        chunk = json.loads(results[0].replace("data: ", ""))
        assert chunk["choices"][0]["delta"]["tool_calls"][0]["function"]["name"] == "get_weather"

        # input_json_delta
        event2 = {
            "type": "content_block_delta",
            "index": 1,
            "delta": {"type": "input_json_delta", "partial_json": '{"city":'},
        }
        results2 = convert_stream_event(event2, state)
        assert len(results2) == 1

    def test_message_stop(self):
        state = {}
        event = {"type": "message_stop"}
        results = convert_stream_event(event, state)
        assert results == ["data: [DONE]\n\n"]

    def test_message_delta_stop_reason(self):
        state = {"id": "chatcmpl-001", "model": "m"}
        event = {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn"},
            "usage": {"output_tokens": 42},
        }
        results = convert_stream_event(event, state)
        chunk = json.loads(results[0].replace("data: ", ""))
        assert chunk["choices"][0]["finish_reason"] == "stop"
