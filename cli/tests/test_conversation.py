"""Conversation 单元测试"""

from cli.conversation import Conversation


class TestConversation:
    def test_add_user(self):
        c = Conversation()
        c.add_user("hello")
        assert len(c) == 1
        assert c.get_messages()[0] == {"role": "user", "content": "hello"}

    def test_add_assistant(self):
        c = Conversation()
        c.add_assistant("hi", tool_calls=[{"name": "f"}])
        msg = c.get_messages()[0]
        assert msg["role"] == "assistant"
        assert msg["tool_calls"] == [{"name": "f"}]

    def test_add_assistant_no_tools(self):
        c = Conversation()
        c.add_assistant("hi")
        msg = c.get_messages()[0]
        assert "tool_calls" not in msg

    def test_add_tool_result(self):
        c = Conversation()
        c.add_tool_result("tc_1", "result")
        msg = c.get_messages()[0]
        assert msg["role"] == "tool"
        assert msg["tool_call_id"] == "tc_1"

    def test_clear(self):
        c = Conversation()
        c.add_user("hello")
        c.add_assistant("hi")
        c.clear()
        assert len(c) == 0

    def test_get_messages_is_copy(self):
        c = Conversation()
        c.add_user("hello")
        msgs = c.get_messages()
        msgs.append({"role": "user", "content": "extra"})
        assert len(c) == 1
