"""openai_to_claude 转换器单元测试"""

import json
from unittest.mock import MagicMock

import pytest
from app.converters.openai_to_claude import OpenAIToClaudeConverter


@pytest.fixture
def converter():
    return OpenAIToClaudeConverter()


# ── convert_request ────────────────────────────────────────

class TestConvertRequest:
    def test_simple_text(self, converter):
        req = {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Hello"}],
        }
        result = converter.convert_request(req)
        assert result["model"] == "claude-sonnet-4-6-20250514"
        assert result["messages"][0]["role"] == "user"
        assert result["messages"][0]["content"] == [{"type": "text", "text": "Hello"}]
        assert result["max_tokens"] == 4096

    def test_system_message_extracted(self, converter):
        req = {
            "model": "gpt-4",
            "messages": [
                {"role": "system", "content": "You are helpful"},
                {"role": "user", "content": "Hi"},
            ],
        }
        result = converter.convert_request(req)
        assert result["system"] == "You are helpful"
        assert len(result["messages"]) == 1
        assert result["messages"][0]["role"] == "user"

    def test_max_tokens_passthrough(self, converter):
        req = {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 1000,
        }
        result = converter.convert_request(req)
        assert result["max_tokens"] == 1000

    def test_optional_params(self, converter):
        req = {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Hi"}],
            "temperature": 0.7,
            "top_p": 0.9,
            "stop": ["END"],
            "stream": True,
        }
        result = converter.convert_request(req)
        assert result["temperature"] == 0.7
        assert result["top_p"] == 0.9
        assert result["stop_sequences"] == ["END"]
        assert result["stream"] is True

    def test_stop_string_to_list(self, converter):
        req = {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Hi"}],
            "stop": "STOP",
        }
        result = converter.convert_request(req)
        assert result["stop_sequences"] == ["STOP"]

    def test_tools_conversion(self, converter):
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
        result = converter.convert_request(req)
        assert result["tools"][0]["name"] == "get_weather"
        assert result["tools"][0]["input_schema"]["type"] == "object"

    def test_tool_choice_auto(self, converter):
        req = {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Hi"}],
            "tools": [{"type": "function", "function": {"name": "f", "parameters": {}}}],
            "tool_choice": "auto",
        }
        result = converter.convert_request(req)
        assert result["tool_choice"] == {"type": "auto"}

    def test_tool_choice_required(self, converter):
        req = {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Hi"}],
            "tools": [{"type": "function", "function": {"name": "f", "parameters": {}}}],
            "tool_choice": "required",
        }
        result = converter.convert_request(req)
        assert result["tool_choice"] == {"type": "any"}

    def test_tool_choice_specific(self, converter):
        req = {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Hi"}],
            "tools": [{"type": "function", "function": {"name": "get_weather", "parameters": {}}}],
            "tool_choice": {"type": "function", "function": {"name": "get_weather"}},
        }
        result = converter.convert_request(req)
        assert result["tool_choice"] == {"type": "tool", "name": "get_weather"}

    def test_assistant_with_tool_calls(self, converter):
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
        result = converter.convert_request(req)
        assistant_msg = result["messages"][1]
        assert assistant_msg["role"] == "assistant"
        assert assistant_msg["content"][0]["type"] == "tool_use"
        assert assistant_msg["content"][0]["input"] == {"city": "Beijing"}
        tool_msg = result["messages"][2]
        assert tool_msg["role"] == "user"
        assert tool_msg["content"][0]["type"] == "tool_result"
        assert tool_msg["content"][0]["tool_use_id"] == "call_123"

    def test_model_passthrough(self, converter):
        req = {
            "model": "unknown-model",
            "messages": [{"role": "user", "content": "Hi"}],
        }
        result = converter.convert_request(req)
        assert result["model"] == "unknown-model"

    def test_multi_turn(self, converter):
        req = {
            "model": "gpt-4o",
            "messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
                {"role": "user", "content": "How are you?"},
            ],
        }
        result = converter.convert_request(req)
        assert len(result["messages"]) == 3


# ── convert_response ──────────────────────────────────────

def _mock_message(id="msg_abc", model="claude-sonnet-4-6-20250514", content=None, stop_reason="end_turn", input_tokens=10, output_tokens=5):
    """构造模拟的 anthropic.types.Message 对象"""
    msg = MagicMock()
    msg.id = id
    msg.model = model
    msg.content = content or []
    msg.stop_reason = stop_reason
    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens
    msg.usage = usage
    return msg


def _mock_text_block(text):
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def _mock_tool_use_block(id, name, input_data):
    block = MagicMock()
    block.type = "tool_use"
    block.id = id
    block.name = name
    block.input = input_data
    return block


class TestConvertResponse:
    def test_text_response(self, converter):
        resp = _mock_message(content=[_mock_text_block("Hello!")])
        result = converter.convert_response(resp)
        assert result["id"].startswith("chatcmpl-")
        assert result["choices"][0]["message"]["content"] == "Hello!"
        assert result["choices"][0]["finish_reason"] == "stop"
        assert result["usage"]["prompt_tokens"] == 10
        assert result["usage"]["completion_tokens"] == 5
        assert result["usage"]["total_tokens"] == 15

    def test_tool_use_response(self, converter):
        resp = _mock_message(
            content=[
                _mock_text_block("Let me check."),
                _mock_tool_use_block("tu_1", "get_weather", {"city": "Beijing"}),
            ],
            stop_reason="tool_use",
        )
        result = converter.convert_response(resp)
        assert result["choices"][0]["finish_reason"] == "tool_calls"
        tc = result["choices"][0]["message"]["tool_calls"][0]
        assert tc["function"]["name"] == "get_weather"
        assert json.loads(tc["function"]["arguments"]) == {"city": "Beijing"}

    def test_max_tokens_stop(self, converter):
        resp = _mock_message(
            content=[_mock_text_block("partial")],
            stop_reason="max_tokens",
        )
        result = converter.convert_response(resp)
        assert result["choices"][0]["finish_reason"] == "length"


# ── convert_stream_event ──────────────────────────────────

def _mock_stream_event(event_type, **kwargs):
    """构造模拟的 anthropic RawMessageStreamEvent"""
    event = MagicMock()
    event.type = event_type
    for k, v in kwargs.items():
        setattr(event, k, v)
    return event


class TestConvertStreamEvent:
    def test_message_start(self, converter):
        msg = MagicMock()
        msg.id = "msg_001"
        msg.model = "claude-sonnet-4-6-20250514"
        event = _mock_stream_event("message_start", message=msg)
        state = {}
        results = converter.convert_stream_event(event, state)
        assert len(results) == 1
        chunk = json.loads(results[0].replace("data: ", ""))
        assert chunk["choices"][0]["delta"]["role"] == "assistant"

    def test_text_delta(self, converter):
        delta = MagicMock()
        delta.type = "text_delta"
        delta.text = "Hello"
        event = _mock_stream_event("content_block_delta", delta=delta)
        state = {"id": "chatcmpl-001", "model": "m"}
        results = converter.convert_stream_event(event, state)
        assert len(results) == 1
        chunk = json.loads(results[0].replace("data: ", ""))
        assert chunk["choices"][0]["delta"]["content"] == "Hello"

    def test_tool_use_stream(self, converter):
        block = MagicMock()
        block.type = "tool_use"
        block.id = "tu_1"
        block.name = "get_weather"
        event = _mock_stream_event("content_block_start", content_block=block)
        state = {"id": "chatcmpl-001", "model": "m", "tool_call_index": -1}
        results = converter.convert_stream_event(event, state)
        assert len(results) == 1
        chunk = json.loads(results[0].replace("data: ", ""))
        assert chunk["choices"][0]["delta"]["tool_calls"][0]["function"]["name"] == "get_weather"

    def test_message_stop(self, converter):
        event = _mock_stream_event("message_stop")
        state = {}
        results = converter.convert_stream_event(event, state)
        assert results == ["data: [DONE]\n\n"]

    def test_message_delta_stop_reason(self, converter):
        delta = MagicMock()
        delta.stop_reason = "end_turn"
        usage = MagicMock()
        usage.output_tokens = 42
        event = _mock_stream_event("message_delta", delta=delta, usage=usage)
        state = {"id": "chatcmpl-001", "model": "m"}
        results = converter.convert_stream_event(event, state)
        chunk = json.loads(results[0].replace("data: ", ""))
        assert chunk["choices"][0]["finish_reason"] == "stop"
