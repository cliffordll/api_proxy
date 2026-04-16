"""CompletionsFromResponsesConverter 测试"""

import json
from app.converters.completions_from_responses import CompletionsFromResponsesConverter


class TestRequest:
    def test_basic(self):
        c = CompletionsFromResponsesConverter()
        req = c.convert_request({
            "model": "gpt-4o",
            "messages": [
                {"role": "system", "content": "Be nice"},
                {"role": "user", "content": "hi"},
            ],
        })
        assert req["instructions"] == "Be nice"
        assert req["input"][0]["type"] == "message"


class TestResponse:
    def test_basic(self):
        c = CompletionsFromResponsesConverter()
        resp = json.loads(c.convert_response({
            "id": "resp_1", "model": "gpt-4o", "status": "completed",
            "output": [{"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Hi"}]}],
            "usage": {"input_tokens": 5, "output_tokens": 3, "total_tokens": 8},
        }))
        assert resp["choices"][0]["message"]["content"] == "Hi"
        assert resp["choices"][0]["finish_reason"] == "stop"

    def test_function_call(self):
        c = CompletionsFromResponsesConverter()
        resp = json.loads(c.convert_response({
            "id": "resp_2", "model": "gpt-4o", "status": "completed",
            "output": [{"type": "function_call", "call_id": "c1", "name": "f", "arguments": "{}"}],
            "usage": {"input_tokens": 5, "output_tokens": 3, "total_tokens": 8},
        }))
        assert resp["choices"][0]["message"]["tool_calls"][0]["function"]["name"] == "f"
        assert resp["choices"][0]["finish_reason"] == "tool_calls"


class TestStream:
    def test_flow(self):
        c = CompletionsFromResponsesConverter()
        events = [
            '{"type":"response.created","response":{"id":"r1","model":"gpt-4o","status":"in_progress"}}',
            '{"type":"response.output_text.delta","output_index":0,"content_index":0,"delta":"Hi"}',
            '{"type":"response.completed","response":{"id":"r1","model":"gpt-4o","status":"completed","usage":{"input_tokens":5,"output_tokens":3,"total_tokens":8}}}',
        ]
        all_results = []
        for e in events:
            all_results.extend(c.convert_stream_event(e))
        assert any("data: [DONE]" in r for r in all_results)
        chunks = [json.loads(r.split("data: ")[1]) for r in all_results if "[DONE]" not in r]
        assert chunks[0]["choices"][0]["delta"]["role"] == "assistant"
