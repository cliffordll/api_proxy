"""MessagesFromResponsesConverter 测试"""

import json
from app.converters.messages_from_responses import MessagesFromResponsesConverter


class TestRequest:
    def test_basic(self):
        c = MessagesFromResponsesConverter()
        req = c.convert_request({
            "model": "claude-sonnet-4-6-20250514",
            "messages": [{"role": "user", "content": "hi"}],
            "system": "Be nice",
            "max_tokens": 100,
        })
        assert req["instructions"] == "Be nice"
        assert req["input"][0]["content"] == "hi"
        assert req["max_output_tokens"] == 100


class TestResponse:
    def test_text(self):
        c = MessagesFromResponsesConverter()
        resp = c.convert_response({
            "id": "resp_1", "model": "gpt-4o", "status": "completed",
            "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Hi"}]}],
            "usage": {"input_tokens": 5, "output_tokens": 3, "total_tokens": 8},
        })
        assert resp["content"][0]["text"] == "Hi"
        assert resp["stop_reason"] == "end_turn"

    def test_tool_use(self):
        c = MessagesFromResponsesConverter()
        resp = c.convert_response({
            "id": "resp_2", "model": "gpt-4o", "status": "completed",
            "output": [{"type": "function_call", "call_id": "c1", "name": "f", "arguments": "{}"}],
            "usage": {"input_tokens": 5, "output_tokens": 3, "total_tokens": 8},
        })
        assert resp["content"][0]["type"] == "tool_use"
        assert resp["stop_reason"] == "tool_use"


class TestStream:
    def test_flow(self):
        c = MessagesFromResponsesConverter()
        events = [
            '{"type":"response.created","response":{"id":"r1","model":"gpt-4o","status":"in_progress"}}',
            '{"type":"response.output_text.delta","output_index":0,"content_index":0,"delta":"Hi"}',
            '{"type":"response.completed","response":{"id":"r1","model":"gpt-4o","status":"completed","usage":{"input_tokens":5,"output_tokens":3,"total_tokens":8}}}',
        ]
        all_results = []
        for e in events:
            all_results.extend(c.convert_stream_event(e))
        done = c.convert_stream_done()
        all_results.extend(done)

        types = [json.loads(r)["type"] for r in all_results]
        assert "message_start" in types
        assert "message_stop" in types
