"""claude_to_openai 转换器单元测试"""

import json
import pytest
from app.converters.claude_to_openai import convert_request, convert_response, convert_stream_event


# ── convert_request ────────────────────────────────────────

class TestConvertRequest:
    def test_simple_text(self):
        req = {
            "model": "claude-sonnet-4-6-20250514",
            "messages": [{"role": "user", "content": "Hello"}],
            "max_tokens": 1024,
        }
        result = convert_request(req)
        assert result["model"] == "gpt-4o"
        assert result["messages"][0] == {"role": "user", "content": "Hello"}
        assert result["max_tokens"] == 1024

    def test_system_injected(self):
        req = {
            "model": "claude-sonnet-4-6-20250514",
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 1024,
            "system": "You are helpful",
        }
        result = convert_request(req)
        assert result["messages"][0] == {"role": "system", "content": "You are helpful"}
        assert result["messages"][1] == {"role": "user", "content": "Hi"}

    def test_optional_params(self):
        req = {
            "model": "claude-sonnet-4-6-20250514",
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 1024,
            "temperature": 0.5,
            "top_p": 0.8,
            "stop_sequences": ["END"],
            "stream": True,
        }
        result = convert_request(req)
        assert result["temperature"] == 0.5
        assert result["top_p"] == 0.8
        assert result["stop"] == ["END"]
        assert result["stream"] is True

    def test_tools_conversion(self):
        req = {
            "model": "claude-sonnet-4-6-20250514",
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 1024,
            "tools": [{
                "name": "get_weather",
                "description": "Get weather",
                "input_schema": {"type": "object", "properties": {"city": {"type": "string"}}},
            }],
        }
        result = convert_request(req)
        assert result["tools"][0]["type"] == "function"
        assert result["tools"][0]["function"]["name"] == "get_weather"
        assert result["tools"][0]["function"]["parameters"]["type"] == "object"

    def test_tool_choice_any(self):
        req = {
            "model": "claude-sonnet-4-6-20250514",
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 1024,
            "tool_choice": {"type": "any"},
        }
        result = convert_request(req)
        assert result["tool_choice"] == "required"

    def test_tool_choice_specific(self):
        req = {
            "model": "claude-sonnet-4-6-20250514",
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 1024,
            "tool_choice": {"type": "tool", "name": "get_weather"},
        }
        result = convert_request(req)
        assert result["tool_choice"] == {"type": "function", "function": {"name": "get_weather"}}

    def test_tool_use_and_tool_result(self):
        req = {
            "model": "claude-sonnet-4-6-20250514",
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": "What's the weather?"}]},
                {
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "id": "tu_1", "name": "get_weather", "input": {"city": "Beijing"}},
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": "tu_1", "content": "Sunny 25°C"},
                    ],
                },
            ],
            "max_tokens": 1024,
        }
        result = convert_request(req)
        # user text
        assert result["messages"][0] == {"role": "user", "content": "What's the weather?"}
        # assistant tool_calls
        assert result["messages"][1]["role"] == "assistant"
        assert result["messages"][1]["tool_calls"][0]["function"]["name"] == "get_weather"
        # tool result
        assert result["messages"][2]["role"] == "tool"
        assert result["messages"][2]["tool_call_id"] == "tu_1"

    def test_model_passthrough(self):
        req = {
            "model": "unknown-model",
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 1024,
        }
        result = convert_request(req)
        assert result["model"] == "unknown-model"


# ── convert_response ──────────────────────────────────────

class TestConvertResponse:
    def test_text_response(self):
        resp = {
            "id": "chatcmpl-abc",
            "model": "gpt-4o",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": "Hello!"},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        result = convert_response(resp)
        assert result["id"] == "msg_abc"
        assert result["content"][0]["type"] == "text"
        assert result["content"][0]["text"] == "Hello!"
        assert result["stop_reason"] == "end_turn"
        assert result["usage"]["input_tokens"] == 10
        assert result["usage"]["output_tokens"] == 5

    def test_tool_calls_response(self):
        resp = {
            "id": "chatcmpl-xyz",
            "model": "gpt-4o",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Let me check.",
                    "tool_calls": [{
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "get_weather", "arguments": '{"city":"Beijing"}'},
                    }],
                },
                "finish_reason": "tool_calls",
            }],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
        }
        result = convert_response(resp)
        assert result["stop_reason"] == "tool_use"
        assert result["content"][0]["type"] == "text"
        assert result["content"][1]["type"] == "tool_use"
        assert result["content"][1]["input"] == {"city": "Beijing"}

    def test_length_stop(self):
        resp = {
            "id": "chatcmpl-abc",
            "model": "gpt-4o",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "partial"}, "finish_reason": "length"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 100, "total_tokens": 105},
        }
        result = convert_response(resp)
        assert result["stop_reason"] == "max_tokens"


# ── convert_stream_event ──────────────────────────────────

class TestConvertStreamEvent:
    def test_first_chunk_generates_message_start(self):
        state = {}
        line = 'data: {"id":"chatcmpl-001","model":"gpt-4o","choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]}'
        results = convert_stream_event(line, state)
        # 应产生 message_start + content_block_start
        assert any("message_start" in r for r in results)
        assert any("content_block_start" in r for r in results)
        assert state["started"] is True

    def test_text_delta(self):
        state = {"started": True, "content_block_index": 0, "content_block_open": True, "current_tool_index": -1}
        line = 'data: {"id":"chatcmpl-001","model":"gpt-4o","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}'
        results = convert_stream_event(line, state)
        assert any("text_delta" in r for r in results)

    def test_done_generates_stop_events(self):
        state = {"started": True, "content_block_index": 0, "content_block_open": True, "stop_reason": "end_turn", "output_tokens": 10}
        line = "data: [DONE]"
        results = convert_stream_event(line, state)
        assert any("content_block_stop" in r for r in results)
        assert any("message_delta" in r for r in results)
        assert any("message_stop" in r for r in results)

    def test_tool_call_stream(self):
        state = {"started": True, "content_block_index": 0, "content_block_open": True, "current_tool_index": -1}
        line = 'data: {"id":"chatcmpl-001","model":"gpt-4o","choices":[{"index":0,"delta":{"tool_calls":[{"index":0,"id":"call_1","type":"function","function":{"name":"get_weather","arguments":""}}]},"finish_reason":null}]}'
        results = convert_stream_event(line, state)
        assert any("content_block_start" in r and "tool_use" in r for r in results)

    def test_non_data_line_ignored(self):
        state = {}
        results = convert_stream_event(": ping", state)
        assert results == []
