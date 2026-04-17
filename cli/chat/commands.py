"""斜杠命令：执行语义（CommandHandler）+ 输入补全（DynamicCompleter）"""

from __future__ import annotations

import json

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document

from cli.core.display import Display
from common.routes import ROUTES


# 所有斜杠命令（Tab 补全 + /help 范围一致）
COMMANDS = [
    "/help", "/model", "/models", "/route", "/routes",
    "/stream", "/history", "/clear", "/quit", "/exit",
]
STREAM_OPTIONS = ["on", "off"]


class CommandHandler:
    """解析和执行斜杠命令。"""

    def __init__(
        self,
        config: dict,
        conversation,
        display: Display,
        client=None,
        route_results: list[dict] | None = None,
    ):
        self.config = config
        self.conversation = conversation
        self.display = display
        self.client = client
        self.route_results = route_results if route_results is not None else []

    async def handle(self, input_text: str) -> bool:
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
            "/routes": self._cmd_routes,
            "/stream": lambda: self._cmd_stream(arg),
            "/models": self._cmd_models,
            "/history": self._cmd_history,
            "/clear": self._cmd_clear,
        }

        handler = handlers.get(cmd)
        if handler:
            result = handler()
            if hasattr(result, "__await__"):
                await result
            return True

        # /quit /exit 由 REPL 处理
        if cmd in ("/quit", "/exit"):
            return False

        self.display.print_error(f"未知命令: {cmd}，输入 /help 查看帮助")
        return True

    def _cmd_help(self):
        help_text = (
            "/help              显示帮助\n"
            "/route <name>      切换路由 (completions/messages/responses)\n"
            "/routes            列出路由并选择切换\n"
            "/model <name>      切换模型\n"
            "/models            查看可用模型\n"
            "/stream on|off     开关流式\n"
            "/history           查看对话历史\n"
            "/clear             清空对话\n"
            "/quit              退出"
        )
        self.display.print_info(help_text)

    def _cmd_routes(self):
        """列出路由 + 数字选择器（不探测，选中后走切换流水线）。"""
        from cli.core.config import load_routes
        from common.routes import ROUTE_PRIORITY

        direct = self.config.get("base_url_override")
        if direct:
            # 直连场景：路由名已自带协议语义（completions/responses/messages），picker 不显示 provider
            entries = [(r, None) for r in ROUTE_PRIORITY]
        else:
            routes = load_routes()
            entries = [(name, conf.get("provider")) for name, conf in routes.items()]

        if not entries:
            self.display.print_error("未找到路由配置")
            return

        idx = self.display.print_route_picker(entries, current=self.config.get("route"))
        if idx is None:
            return
        selected = entries[idx][0]
        label = "协议" if direct else "路由"
        if selected == self.config["route"]:
            self.display.print_info(f"{label}未变: {selected}")
            return
        self.config["route"] = selected
        self.display.print_info(f"{label}已切换: {selected}")

    def _cmd_models(self):
        """列出当前路由的模型（从启动探测缓存读），数字选择器切换模型。"""
        route = self.config["route"]
        result = next((r for r in self.route_results if r["route"] == route), None)
        upstream = result and result.get("base_url")
        models = (result and result.get("models")) or []
        if not models:
            self.display.print_models(None, upstream=upstream)
            return
        self.display.print_models(
            models, numbered=True, upstream=upstream, current=self.config.get("model")
        )
        try:
            choice = input("选择模型 (输入编号，回车跳过): ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if not choice:
            return
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(models):
                self.config["model"] = models[idx]
                self.display.print_info(f"模型已切换: {models[idx]}")
            else:
                self.display.print_error(f"无效编号: {choice}")
        except ValueError:
            self.display.print_error(f"无效输入: {choice}")

    def _cmd_model(self, name: str):
        if not name:
            self.display.print_info(f"当前模型: {self.config['model']}")
            return
        self.config["model"] = name
        self.display.print_info(f"模型已切换: {name}")

    def _cmd_route(self, name: str):
        from common.routes import ROUTES

        label = "协议" if self.config.get("base_url_override") else "路由"
        if not name:
            self.display.print_info(f"当前{label}: {self.config['route']}")
            return
        if name not in ROUTES:
            self.display.print_error(f"无效{label}: {name}，可选: {', '.join(ROUTES)}")
            return
        self.config["route"] = name
        self.display.print_info(f"{label}已切换: {name}")

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


class DynamicCompleter(Completer):
    """根据输入上下文动态补全：
    - 首 token 补 COMMANDS
    - 次 token 按命令分派（model / route / stream）
    """

    def __init__(self, models: list[str] | None = None):
        self.models = models or []

    def get_completions(self, document: Document, complete_event):
        text = document.text_before_cursor
        words = text.split()

        if not text or text == "/":
            for cmd in COMMANDS:
                if cmd.startswith(text):
                    yield Completion(cmd, start_position=-len(text))
            return

        if len(words) == 1 and text.startswith("/") and not text.endswith(" "):
            for cmd in COMMANDS:
                if cmd.startswith(words[0]):
                    yield Completion(cmd, start_position=-len(words[0]))
            return

        cmd = words[0].lower()
        partial = words[1] if len(words) >= 2 else ""
        source = {
            "/model": self.models,
            "/route": ROUTES,
            "/stream": STREAM_OPTIONS,
        }.get(cmd)
        if not source:
            return
        for item in source:
            if item.startswith(partial):
                yield Completion(item, start_position=-len(partial))
