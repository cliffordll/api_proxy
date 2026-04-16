"""CommandHandler 单元测试"""

from cli.commands import CommandHandler
from cli.conversation import Conversation
from cli.display import Display


def _make_handler():
    config = {"model": "test-model", "route": "messages", "stream": True}
    conv = Conversation()
    display = Display()
    return CommandHandler(config, conv, display), config, conv


class TestCommandHandler:
    def test_non_command(self):
        handler, _, _ = _make_handler()
        assert handler.handle("hello") is False

    def test_help(self):
        handler, _, _ = _make_handler()
        assert handler.handle("/help") is True

    def test_model_switch(self):
        handler, config, _ = _make_handler()
        handler.handle("/model gpt-4o")
        assert config["model"] == "gpt-4o"

    def test_model_show(self):
        handler, _, _ = _make_handler()
        assert handler.handle("/model") is True

    def test_route_switch(self):
        handler, config, _ = _make_handler()
        handler.handle("/route completions")
        assert config["route"] == "completions"

    def test_route_invalid(self):
        handler, config, _ = _make_handler()
        handler.handle("/route invalid")
        assert config["route"] == "messages"  # unchanged

    def test_stream_on_off(self):
        handler, config, _ = _make_handler()
        handler.handle("/stream off")
        assert config["stream"] is False
        handler.handle("/stream on")
        assert config["stream"] is True

    def test_clear(self):
        handler, _, conv = _make_handler()
        conv.add_user("hello")
        handler.handle("/clear")
        assert len(conv) == 0

    def test_history(self):
        handler, _, conv = _make_handler()
        conv.add_user("hello")
        assert handler.handle("/history") is True

    def test_quit_not_handled(self):
        handler, _, _ = _make_handler()
        assert handler.handle("/quit") is False

    def test_unknown_command(self):
        handler, _, _ = _make_handler()
        assert handler.handle("/unknown") is True
