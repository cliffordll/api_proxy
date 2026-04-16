"""MockupClient 测试"""

import pytest
from app.clients.mockup_client import MockupClient


class TestNonStream:
    @pytest.mark.asyncio
    async def test_messages(self):
        c = MockupClient(base_url="http://x", interface="messages")
        result = await c.chat({"model": "test"}, "key", stream=False)
        assert result["type"] == "message"
        assert result["content"][0]["type"] == "text"
        assert "[mockup]" in result["content"][0]["text"]

    @pytest.mark.asyncio
    async def test_completions(self):
        c = MockupClient(base_url="http://x", interface="completions")
        result = await c.chat({"model": "test"}, "key", stream=False)
        assert result["object"] == "chat.completion"
        assert "[mockup]" in result["choices"][0]["message"]["content"]

    @pytest.mark.asyncio
    async def test_responses(self):
        c = MockupClient(base_url="http://x", interface="responses")
        result = await c.chat({"model": "test"}, "key", stream=False)
        assert result["object"] == "response"
        assert result["status"] == "completed"


class TestStream:
    @pytest.mark.asyncio
    async def test_messages_stream(self):
        c = MockupClient(base_url="http://x", interface="messages")
        stream = c._mock_messages({"model": "test"}, stream=True)
        items = [item async for item in stream]
        assert len(items) > 3

    @pytest.mark.asyncio
    async def test_completions_stream(self):
        c = MockupClient(base_url="http://x", interface="completions")
        stream = c._mock_completions({"model": "test"}, stream=True)
        items = [item async for item in stream]
        assert items[-1] == "[DONE]"

    @pytest.mark.asyncio
    async def test_responses_stream(self):
        c = MockupClient(base_url="http://x", interface="responses")
        stream = c._mock_responses({"model": "test"}, stream=True)
        items = [item async for item in stream]
        assert len(items) > 3
