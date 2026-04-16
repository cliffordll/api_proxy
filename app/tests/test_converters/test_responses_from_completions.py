"""ResponsesFromCompletionsConverter 测试"""

import json
from app.converters.responses_from_completions import ResponsesFromCompletionsConverter


class TestRequest:
    def test_basic(self):
        c = ResponsesFromCompletionsConverter()
        req = c.convert_request({"model": "gpt-4o", "input": "hi", "instructions": "Be nice"})
        assert req["messages"][0]["role"] == "system"
        assert req["messages"][1]["content"] == "hi"


class TestResponse:
    def test_basic(self):
        c = ResponsesFromCompletionsConverter()
        resp = json.loads(c.convert_response({
            "id": "chatcmpl-1", "model": "gpt-4o",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "Hello"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        }))
        assert resp["status"] == "completed"
        assert resp["output"][0]["content"][0]["text"] == "Hello"


class TestStream:
    def test_done(self):
        c = ResponsesFromCompletionsConverter()
        c._stream_state  # init state
        results = c.convert_stream_event("[DONE]")
        assert any("response.completed" in r for r in results)
