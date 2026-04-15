"""claude_to_openai 转换器单元测试"""

import json
from unittest.mock import MagicMock

import pytest
from anthropic.types import Message
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice
from openai.types.chat.chat_completion_message_tool_call import ChatCompletionMessageToolCall, Function
from openai.types import CompletionUsage
from app.converters.claude_to_openai import ClaudeToOpenAIConverter


@pytest.fixture
def converter():
    return ClaudeToOpenAIConverter()


# ── convert_request ────────────────────────────────────────

class TestConvertRequest:
    def test_simple_text(self, converter):
        req = {
            "model": "claude-sonnet-4-6-20250514",
            "messages": [{"role": "user", "content": "Hello"}],
            "max_tokens": 1024,
        }
        result = converter.convert_request(req)
        assert result["model"] == "gpt-4o"
        assert result["messages"][0] == {"role": "user", "content": "Hello"}
        assert result["max_tokens"] == 1024

    def test_system_injected(self, converter):
        req = {
            "model": "claude-sonnet-4-6-20250514",
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 1024,
            "system": "You are helpful",
        }
        result = converter.convert_request(req)
        assert result["messages"][0] == {"role": "system", "content": "You are helpful"}
        assert result["messages"][1] == {"role": "user", "content": "Hi"}

    def test_optional_params(self, converter):
        req = {
            "model": "claude-sonnet-4-6-20250514",
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 1024,
            "temperature": 0.5,
            "top_p": 0.8,
            "stop_sequences": ["END"],
            "stream": True,
        }
        result = converter.convert_request(req)
        assert result["temperature"] == 0.5
        assert result["top_p"] == 0.8
        assert result["stop"] == ["END"]
        assert result["stream"] is True

    def test_tools_conversion(self, converter):
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
        result = converter.convert_request(req)
        assert result["tools"][0]["type"] == "function"
        assert result["tools"][0]["function"]["name"] == "get_weather"

    def test_tool_choice_any(self, converter):
        req = {
            "model": "claude-sonnet-4-6-20250514",
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 1024,
            "tool_choice": {"type": "any"},
        }
        result = converter.convert_request(req)
        assert result["tool_choice"] == "required"

    def test_tool_choice_specific(self, converter):
        req = {
            "model": "claude-sonnet-4-6-20250514",
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 1024,
            "tool_choice": {"type": "tool", "name": "get_weather"},
        }
        result = converter.convert_request(req)
        assert result["tool_choice"] == {"type": "function", "function": {"name": "get_weather"}}

    def test_tool_use_and_tool_result(self, converter):
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
        result = converter.convert_request(req)
        assert result["messages"][0] == {"role": "user", "content": "What's the weather?"}
        assert result["messages"][1]["role"] == "assistant"
        assert result["messages"][1]["tool_calls"][0]["function"]["name"] == "get_weather"
        assert result["messages"][2]["role"] == "tool"
        assert result["messages"][2]["tool_call_id"] == "tu_1"

    def test_model_passthrough(self, converter):
        req = {
            "model": "unknown-model",
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 1024,
        }
        result = converter.convert_request(req)
        assert result["model"] == "unknown-model"


# ── convert_response (returns anthropic.types.Message) ────

def _mock_completion(id="chatcmpl-abc", model="gpt-4o", content="Hello!", tool_calls=None, finish_reason="stop", prompt_tokens=10, completion_tokens=5):
    """构造真实的 openai.types.chat.ChatCompletion"""
    tc_list = None
    if tool_calls:
        tc_list = tool_calls
    return ChatCompletion(
        id=id,
        object="chat.completion",
        created=0,
        model=model,
        choices=[Choice(
            index=0,
            message=ChatCompletionMessage(
                role="assistant",
                content=content,
                tool_calls=tc_list,
            ),
            finish_reason=finish_reason,
        )],
        usage=CompletionUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )


def _mock_tool_call(id, name, arguments):
    return ChatCompletionMessageToolCall(
        id=id,
        type="function",
        function=Function(name=name, arguments=arguments),
    )


class TestConvertResponse:
    def test_text_response(self, converter):
        resp = _mock_completion()
        result = converter.convert_response(resp)
        assert isinstance(result, Message)
        assert result.id == "msg_abc"
        assert result.content[0].type == "text"
        assert result.content[0].text == "Hello!"
        assert result.stop_reason == "end_turn"
        assert result.usage.input_tokens == 10
        assert result.usage.output_tokens == 5

    def test_tool_calls_response(self, converter):
        tc = _mock_tool_call("call_1", "get_weather", '{"city":"Beijing"}')
        resp = _mock_completion(
            id="chatcmpl-xyz",
            content="Let me check.",
            tool_calls=[tc],
            finish_reason="tool_calls",
        )
        result = converter.convert_response(resp)
        assert isinstance(result, Message)
        assert result.stop_reason == "tool_use"
        assert result.content[0].type == "text"
        assert result.content[1].type == "tool_use"
        assert result.content[1].input == {"city": "Beijing"}

    def test_length_stop(self, converter):
        resp = _mock_completion(content="partial", finish_reason="length")
        result = converter.convert_response(resp)
        assert isinstance(result, Message)
        assert result.stop_reason == "max_tokens"


# ── convert_stream_event ──────────────────────────────────

def _mock_chunk(id="chatcmpl-001", model="gpt-4o", content=None, tool_calls=None, finish_reason=None, usage=None):
    """构造模拟的 ChatCompletionChunk"""
    from openai.types.chat import ChatCompletionChunk
    from openai.types.chat.chat_completion_chunk import Choice as ChunkChoice, ChoiceDelta

    chunk = MagicMock(spec=ChatCompletionChunk)
    chunk.id = id
    chunk.model = model
    chunk.usage = usage

    delta = MagicMock(spec=ChoiceDelta)
    delta.content = content
    delta.tool_calls = tool_calls

    choice = MagicMock(spec=ChunkChoice)
    choice.delta = delta
    choice.finish_reason = finish_reason

    chunk.choices = [choice]
    return chunk


class TestConvertStreamEvent:
    def test_first_chunk_generates_message_start(self, converter):
        state = {}
        chunk = _mock_chunk()
        chunk.choices[0].delta.content = None
        chunk.choices[0].delta.tool_calls = None
        results = converter.convert_stream_event(chunk, state)
        assert any("message_start" in r for r in results)
        assert any("content_block_start" in r for r in results)
        assert state["started"] is True

    def test_text_delta(self, converter):
        state = {"started": True, "content_block_index": 0, "content_block_open": True, "current_tool_index": -1}
        chunk = _mock_chunk(content="Hello")
        chunk.choices[0].delta.tool_calls = None
        chunk.choices[0].finish_reason = None
        results = converter.convert_stream_event(chunk, state)
        assert any("text_delta" in r for r in results)

    def test_tool_call_stream(self, converter):
        state = {"started": True, "content_block_index": 0, "content_block_open": True, "current_tool_index": -1}

        tc = MagicMock()
        tc.index = 0
        tc.id = "call_1"
        tc.function = MagicMock()
        tc.function.name = "get_weather"
        tc.function.arguments = ""

        chunk = _mock_chunk()
        chunk.choices[0].delta.content = None
        chunk.choices[0].delta.tool_calls = [tc]
        chunk.choices[0].finish_reason = None

        results = converter.convert_stream_event(chunk, state)
        assert any("content_block_start" in r and "tool_use" in r for r in results)

    def test_non_empty_choices(self, converter):
        state = {}
        chunk = _mock_chunk()
        chunk.choices[0].delta.content = None
        chunk.choices[0].delta.tool_calls = None
        results = converter.convert_stream_event(chunk, state)
        assert len(results) > 0


class TestConvertStreamDone:
    def test_generates_stop_events(self, converter):
        state = {"content_block_open": True, "content_block_index": 0, "stop_reason": "end_turn", "output_tokens": 10}
        results = converter.convert_stream_done(state)
        assert any("content_block_stop" in r for r in results)
        assert any("message_delta" in r for r in results)
        assert any("message_stop" in r for r in results)
