"""ChatClient 单元测试"""

from cli.core.client import ChatClient


class TestBuildRequest:
    def test_completions(self):
        c = ChatClient("http://localhost:8000", "completions", "key123")
        body = c._build_body([{"role": "user", "content": "hi"}], "gpt-4o", stream=False)
        assert c._path == "/v1/chat/completions"
        assert c._http.headers["Authorization"] == "Bearer key123"
        assert body["model"] == "gpt-4o"
        assert body["messages"][0]["content"] == "hi"

    def test_messages(self):
        c = ChatClient("http://localhost:8000", "messages", "key123")
        body = c._build_body([{"role": "user", "content": "hi"}], "claude", stream=True)
        assert c._path == "/v1/messages"
        assert c._http.headers["x-api-key"] == "key123"
        assert body["stream"] is True
        assert body["max_tokens"] == 4096

    def test_responses(self):
        c = ChatClient("http://localhost:8000", "responses", "key123")
        body = c._build_body([{"role": "user", "content": "hi"}], "gpt-4o", stream=False)
        assert c._path == "/v1/responses"
        assert "input" in body


class TestParseResponse:
    def test_completions(self):
        c = ChatClient("http://x", "completions", "k")
        text, tools = c.parse_response({
            "choices": [{"message": {"content": "hello", "tool_calls": None}}]
        })
        assert text == "hello"
        assert tools is None

    def test_messages(self):
        c = ChatClient("http://x", "messages", "k")
        text, tools = c.parse_response({
            "content": [{"type": "text", "text": "hello"}]
        })
        assert text == "hello"
        assert tools is None

    def test_responses(self):
        c = ChatClient("http://x", "responses", "k")
        text, tools = c.parse_response({
            "output": [{"type": "message", "content": [{"type": "output_text", "text": "hello"}]}]
        })
        assert text == "hello"

    def test_completions_tool_calls(self):
        c = ChatClient("http://x", "completions", "k")
        text, tools = c.parse_response({
            "choices": [{"message": {
                "content": None,
                "tool_calls": [{"function": {"name": "f", "arguments": "{}"}}]
            }}]
        })
        assert tools is not None
        assert len(tools) == 1


class TestParseStreamChunk:
    def test_completions(self):
        c = ChatClient("http://x", "completions", "k")
        assert c.parse_stream_chunk('{"choices":[{"delta":{"content":"hi"}}]}') == "hi"

    def test_messages(self):
        c = ChatClient("http://x", "messages", "k")
        assert c.parse_stream_chunk('{"type":"content_block_delta","delta":{"type":"text_delta","text":"hi"}}') == "hi"

    def test_responses(self):
        c = ChatClient("http://x", "responses", "k")
        assert c.parse_stream_chunk('{"type":"response.output_text.delta","delta":"hi"}') == "hi"

    def test_invalid_json(self):
        c = ChatClient("http://x", "completions", "k")
        assert c.parse_stream_chunk("not json") is None
