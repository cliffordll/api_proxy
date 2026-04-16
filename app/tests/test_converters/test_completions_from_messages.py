"""CompletionsFromMessagesConverter 测试"""

import json

from app.converters.completions_from_messages import CompletionsFromMessagesConverter


class TestRequest:
    def test_basic(self):
        c = CompletionsFromMessagesConverter()
        req = c.convert_request({
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "hi"}],
        })
        assert req["model"] == "claude-sonnet-4-6-20250514"
        assert req["messages"][0]["role"] == "user"
        assert "max_tokens" in req

    def test_system_extracted(self):
        c = CompletionsFromMessagesConverter()
        req = c.convert_request({
            "model": "gpt-4o",
            "messages": [
                {"role": "system", "content": "Be helpful"},
                {"role": "user", "content": "hi"},
            ],
        })
        assert req["system"] == "Be helpful"
        assert len(req["messages"]) == 1

    def test_tools(self):
        c = CompletionsFromMessagesConverter()
        req = c.convert_request({
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "hi"}],
            "tools": [{"type": "function", "function": {"name": "get_weather", "description": "d", "parameters": {}}}],
            "tool_choice": "auto",
        })
        assert req["tools"][0]["name"] == "get_weather"
        assert req["tool_choice"]["type"] == "auto"


class TestResponse:
    def test_basic(self):
        c = CompletionsFromMessagesConverter()
        resp = json.loads(c.convert_response({
            "id": "msg_1", "model": "claude", "role": "assistant",
            "content": [{"type": "text", "text": "Hi!"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }))
        assert resp["id"] == "chatcmpl-msg_1"
        assert resp["choices"][0]["finish_reason"] == "stop"
        assert resp["choices"][0]["message"]["content"] == "Hi!"
        assert resp["usage"]["total_tokens"] == 15

    def test_tool_use(self):
        c = CompletionsFromMessagesConverter()
        resp = json.loads(c.convert_response({
            "id": "msg_2", "model": "claude", "role": "assistant",
            "content": [{"type": "tool_use", "id": "tu_1", "name": "get_weather", "input": {"city": "NY"}}],
            "stop_reason": "tool_use",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }))
        tc = resp["choices"][0]["message"]["tool_calls"][0]
        assert tc["function"]["name"] == "get_weather"
        assert resp["choices"][0]["finish_reason"] == "tool_calls"


class TestStream:
    def test_full_flow(self):
        c = CompletionsFromMessagesConverter()
        events = [
            '{"type":"message_start","message":{"id":"msg_1","model":"claude","content":[],"usage":{"input_tokens":10,"output_tokens":0}}}',
            '{"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hi"}}',
            '{"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":5}}',
            '{"type":"message_stop"}',
        ]
        all_results = []
        for e in events:
            all_results.extend(c.convert_stream_event(e))

        # 应有: role chunk, content chunk, finish chunk, [DONE]
        assert len(all_results) == 4
        assert all_results[0].startswith("data: ")
        first = json.loads(all_results[0].split("data: ")[1])
        assert first["choices"][0]["delta"]["role"] == "assistant"
        assert "data: [DONE]" in all_results[-1]
