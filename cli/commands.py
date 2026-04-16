"""斜杠命令处理"""

from __future__ import annotations

import json

from cli.display import Display


class CommandHandler:
    """解析和执行斜杠命令。"""

    def __init__(self, config: dict, conversation, display: Display):
        self.config = config
        self.conversation = conversation
        self.display = display

    def handle(self, input_text: str) -> bool:
        """处理斜杠命令，返回 True 表示已处理。"""
        if not input_text.startswith("/"):
            return False

        parts = input_text.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        handlers = {
            "/help": self._cmd_help,
            "/model": lambda: self._cmd_model(arg),
            "/route": lambda: self._cmd_route(arg),
            "/stream": lambda: self._cmd_stream(arg),
            "/history": self._cmd_history,
            "/clear": self._cmd_clear,
        }

        handler = handlers.get(cmd)
        if handler:
            handler()
            return True

        # /quit /exit 由 REPL 处理
        if cmd in ("/quit", "/exit"):
            return False

        self.display.print_error(f"未知命令: {cmd}，输入 /help 查看帮助")
        return True

    def _cmd_help(self):
        help_text = (
            "/help              显示帮助\n"
            "/model <name>      切换模型\n"
            "/route <name>      切换路由 (completions/messages/responses)\n"
            "/stream on|off     开关流式\n"
            "/history           查看对话历史\n"
            "/clear             清空对话\n"
            "/quit              退出"
        )
        self.display.print_info(help_text)

    def _cmd_model(self, name: str):
        if not name:
            self.display.print_info(f"当前模型: {self.config['model']}")
            return
        self.config["model"] = name
        self.display.print_info(f"模型已切换: {name}")

    def _cmd_route(self, name: str):
        if not name:
            self.display.print_info(f"当前路由: {self.config['route']}")
            return
        valid = ("completions", "messages", "responses")
        if name not in valid:
            self.display.print_error(f"无效路由: {name}，可选: {', '.join(valid)}")
            return
        self.config["route"] = name
        # 更新 client 的 route
        self.display.print_info(f"路由已切换: {name}")

    def _cmd_stream(self, arg: str):
        if not arg:
            self.display.print_info(f"流式: {'on' if self.config['stream'] else 'off'}")
            return
        if arg == "on":
            self.config["stream"] = True
            self.display.print_info("流式已开启")
        elif arg == "off":
            self.config["stream"] = False
            self.display.print_info("流式已关闭")
        else:
            self.display.print_error("用法: /stream on|off")

    def _cmd_history(self):
        messages = self.conversation.get_messages()
        if not messages:
            self.display.print_info("对话历史为空")
            return
        for i, msg in enumerate(messages):
            role = msg["role"]
            content = msg.get("content", "")
            if isinstance(content, str):
                text = content[:100] + "..." if len(content) > 100 else content
            else:
                text = json.dumps(content, ensure_ascii=False)[:100] + "..."
            self.display.print_info(f"[{i}] {role}: {text}")

    def _cmd_clear(self):
        self.conversation.clear()
        self.display.print_info("对话已清空")
