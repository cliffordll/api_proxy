"""MessagesFromCompletionsConverter 测试"""

import json
from app.converters.messages_from_completions import MessagesFromCompletionsConverter


class TestRequest:
    def test_basic(self):
        c = MessagesFromCompletionsConverter()
        req = c.convert_request({
            "model": "claude-sonnet-4-6-20250514",
            "messages": [{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
            "max_tokens": 1024,
        })
        assert req["model"] == "claude-sonnet-4-6-20250514"
        assert req["messages"][0]["role"] == "user"

    def test_system(self):
        c = MessagesFromCompletionsConverter()
        req = c.convert_request({
            "model": "claude-sonnet-4-6-20250514",
            "system": "Be helpful",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 100,
        })
        assert req["messages"][0]["role"] == "system"
        assert req["messages"][0]["content"] == "Be helpful"

    def test_tool_choice(self):
        c = MessagesFromCompletionsConverter()
        req = c.convert_request({
            "model": "claude-sonnet-4-6-20250514",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 100,
            "tool_choice": {"type": "any"},
        })
        assert req["tool_choice"] == "required"


class TestResponse:
    def test_basic(self):
        c = MessagesFromCompletionsConverter()
        resp = json.loads(c.convert_response({
            "id": "chatcmpl-abc", "model": "gpt-4o",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hello!"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        }))
        assert resp["id"] == "msg_abc"
        assert resp["content"][0]["text"] == "Hello!"
        assert resp["stop_reason"] == "end_turn"
        assert resp["usage"]["input_tokens"] == 5

    def test_tool_calls(self):
        c = MessagesFromCompletionsConverter()
        resp = json.loads(c.convert_response({
            "id": "chatcmpl-abc", "model": "gpt-4o",
            "choices": [{"index": 0, "message": {
                "role": "assistant", "content": None,
                "tool_calls": [{"id": "tc_1", "type": "function", "function": {"name": "f", "arguments": "{}"}}],
            }, "finish_reason": "tool_calls"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        }))
        assert resp["content"][0]["type"] == "tool_use"
        assert resp["stop_reason"] == "tool_use"


class TestStream:
    def test_full_flow(self):
        c = MessagesFromCompletionsConverter()
        chunks = [
            '{"id":"chatcmpl-x","model":"gpt-4o","choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]}',
            '{"id":"chatcmpl-x","model":"gpt-4o","choices":[{"index":0,"delta":{"content":"Hi"},"finish_reason":null}]}',
            '{"id":"chatcmpl-x","model":"gpt-4o","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}',
        ]
        all_results = []
        for ch in chunks:
            all_results.extend(c.convert_stream_event(ch))
        done = c.convert_stream_done()
        all_results.extend(done)

        types = [json.loads(r.split("data: ")[1])["type"] for r in all_results]
        assert "message_start" in types
        assert "content_block_start" in types
        assert "content_block_delta" in types
        assert "content_block_stop" in types
        assert "message_delta" in types
        assert "message_stop" in types

    def test_done_marker_ignored(self):
        c = MessagesFromCompletionsConverter()
        assert c.convert_stream_event("[DONE]") == []
