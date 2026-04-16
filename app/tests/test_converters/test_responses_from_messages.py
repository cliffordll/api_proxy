"""ResponsesFromMessagesConverter 测试"""

import json
from app.converters.responses_from_messages import ResponsesFromMessagesConverter


class TestRequest:
    def test_string_input(self):
        c = ResponsesFromMessagesConverter()
        req = c.convert_request({"model": "gpt-4o", "input": "hello", "instructions": "Be nice"})
        assert req["system"] == "Be nice"
        assert req["messages"][0]["role"] == "user"

    def test_array_input(self):
        c = ResponsesFromMessagesConverter()
        req = c.convert_request({
            "model": "gpt-4o",
            "input": [{"type": "message", "role": "user", "content": "hi"}],
        })
        assert len(req["messages"]) == 1


class TestResponse:
    def test_text(self):
        c = ResponsesFromMessagesConverter()
        resp = json.loads(c.convert_response({
            "id": "msg_1", "model": "claude",
            "content": [{"type": "text", "text": "Hi!"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }))
        assert resp["status"] == "completed"
        assert resp["output"][0]["type"] == "message"

    def test_tool_use(self):
        c = ResponsesFromMessagesConverter()
        resp = json.loads(c.convert_response({
            "id": "msg_2", "model": "claude",
            "content": [{"type": "tool_use", "id": "tu_1", "name": "f", "input": {}}],
            "stop_reason": "tool_use",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }))
        assert resp["output"][0]["type"] == "function_call"


class TestStream:
    def test_full_flow(self):
        c = ResponsesFromMessagesConverter()
        events = [
            '{"type":"message_start","message":{"id":"msg_1","model":"claude","content":[],"usage":{"input_tokens":0,"output_tokens":0}}}',
            '{"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}',
            '{"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hi"}}',
            '{"type":"content_block_stop","index":0}',
            '{"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":5}}',
            '{"type":"message_stop"}',
        ]
        all_results = []
        for e in events:
            all_results.extend(c.convert_stream_event(e))
        types = [json.loads(r.split("data: ")[1])["type"] for r in all_results]
        assert "response.created" in types
        assert "response.output_text.delta" in types
        assert "response.completed" in types
