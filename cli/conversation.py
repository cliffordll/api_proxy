"""多轮对话历史管理"""

from __future__ import annotations


class Conversation:
    """维护对话历史，支持多轮上下文。"""

    def __init__(self):
        self.history: list[dict] = []

    def add_user(self, content: str) -> None:
        self.history.append({"role": "user", "content": content})

    def add_assistant(self, content: str, tool_calls: list[dict] | None = None) -> None:
        msg = {"role": "assistant", "content": content}
        if tool_calls:
            msg["tool_calls"] = tool_calls
        self.history.append(msg)

    def add_tool_result(self, tool_call_id: str, result: str) -> None:
        self.history.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": result,
        })

    def get_messages(self) -> list[dict]:
        return self.history.copy()

    def clear(self) -> None:
        self.history.clear()

    def __len__(self) -> int:
        return len(self.history)
