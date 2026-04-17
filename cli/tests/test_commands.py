"""CommandHandler 单元测试"""

import pytest

from cli.chat.commands import CommandHandler
from cli.chat.conversation import Conversation
from cli.core.display import Display


def _make_handler():
    config = {"model": "test-model", "route": "messages", "stream": True}
    conv = Conversation()
    display = Display()
    return CommandHandler(config, conv, display), config, conv


class TestCommandHandler:
    @pytest.mark.asyncio
    async def test_non_command(self):
        handler, _, _ = _make_handler()
        assert await handler.handle("hello") is False

    @pytest.mark.asyncio
    async def test_help(self):
        handler, _, _ = _make_handler()
        assert await handler.handle("/help") is True

    @pytest.mark.asyncio
    async def test_model_switch(self):
        handler, config, _ = _make_handler()
        await handler.handle("/model gpt-4o")
        assert config["model"] == "gpt-4o"

    @pytest.mark.asyncio
    async def test_model_show(self):
        handler, _, _ = _make_handler()
        assert await handler.handle("/model") is True

    @pytest.mark.asyncio
    async def test_route_switch(self):
        handler, config, _ = _make_handler()
        await handler.handle("/route completions")
        assert config["route"] == "completions"

    @pytest.mark.asyncio
    async def test_route_invalid(self):
        handler, config, _ = _make_handler()
        await handler.handle("/route invalid")
        assert config["route"] == "messages"  # unchanged

    @pytest.mark.asyncio
    async def test_stream_on_off(self):
        handler, config, _ = _make_handler()
        await handler.handle("/stream off")
        assert config["stream"] is False
        await handler.handle("/stream on")
        assert config["stream"] is True

    @pytest.mark.asyncio
    async def test_clear(self):
        handler, _, conv = _make_handler()
        conv.add_user("hello")
        await handler.handle("/clear")
        assert len(conv) == 0

    @pytest.mark.asyncio
    async def test_history(self):
        handler, _, conv = _make_handler()
        conv.add_user("hello")
        assert await handler.handle("/history") is True

    @pytest.mark.asyncio
    async def test_quit_not_handled(self):
        handler, _, _ = _make_handler()
        assert await handler.handle("/quit") is False

    @pytest.mark.asyncio
    async def test_unknown_command(self):
        handler, _, _ = _make_handler()
        assert await handler.handle("/unknown") is True
