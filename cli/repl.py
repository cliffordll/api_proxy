"""交互式对话循环"""

from __future__ import annotations

import asyncio

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document

from cli.client import ChatClient
from cli.commands import CommandHandler
from cli.conversation import Conversation
from cli.display import Display
from cli.models import load_routes, probe_models


COMMANDS = ["/help", "/model", "/models", "/route", "/stream", "/history", "/clear", "/quit", "/exit"]
ROUTES = ["completions", "messages", "responses"]
STREAM_OPTIONS = ["on", "off"]


class DynamicCompleter(Completer):
    """根据输入上下文动态补全。"""

    def __init__(self, models: list[str] | None = None):
        self.models = models or []

    def get_completions(self, document: Document, complete_event):
        text = document.text_before_cursor
        words = text.split()

        if not text or text == "/":
            # 输入 / 开头 → 补全命令
            for cmd in COMMANDS:
                if cmd.startswith(text):
                    yield Completion(cmd, start_position=-len(text))
        elif len(words) == 1 and text.startswith("/"):
            # 命令输入中
            for cmd in COMMANDS:
                if cmd.startswith(words[0]):
                    yield Completion(cmd, start_position=-len(words[0]))
        elif len(words) >= 2 or (len(words) == 1 and text.endswith(" ")):
            cmd = words[0].lower()
            partial = words[1] if len(words) >= 2 else ""

            if cmd == "/model":
                for m in self.models:
                    if m.startswith(partial):
                        yield Completion(m, start_position=-len(partial))
            elif cmd == "/route":
                for r in ROUTES:
                    if r.startswith(partial):
                        yield Completion(r, start_position=-len(partial))
            elif cmd == "/stream":
                for s in STREAM_OPTIONS:
                    if s.startswith(partial):
                        yield Completion(s, start_position=-len(partial))


class Repl:
    """交互式 REPL，组装 ChatClient + Conversation + CommandHandler + Display。"""

    def __init__(self, config: dict):
        self.config = config
        self.client = ChatClient(
            base_url=config["base_url"],
            route=config["route"],
            api_key=config["api_key"],
        )
        self.conversation = Conversation()
        self.display = Display()
        self.commands = CommandHandler(config, self.conversation, self.display, self.client)
        self.available_models: list[str] = []

    def _build_completer(self) -> DynamicCompleter:
        """构建动态补全器。"""
        return DynamicCompleter(models=self.available_models)

    async def _probe_current_models(self) -> tuple[str | None, list[str] | None]:
        """探测模型。

        - CLI 显式指定了 --base-url：直接打该地址（用户在绕过 Proxy 直连）
        - 否则走 settings.yaml 的 routes[当前路由].base_url（经 Proxy 时的真实上游）

        返回 (upstream, models)。models 为 None 表示探测不可用。
        """
        if self.config.get("base_url_override"):
            upstream = self.config["base_url"]
        else:
            routes = load_routes()
            upstream = routes.get(self.config["route"], {}).get("base_url")
        if not upstream:
            return None, None
        return upstream, await probe_models(upstream)

    async def run(self):
        """主循环。"""
        # 启动时静默探测，塞进 welcome 框内
        upstream, models = await self._probe_current_models()
        self.available_models = models or []
        self.display.print_welcome(
            self.config["base_url"],
            self.config["route"],
            self.config["model"],
            self.config["stream"],
            models,
            upstream,
        )

        session = PromptSession(completer=self._build_completer())

        while True:
            try:
                user_input = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: session.prompt("> ")
                )
                user_input = user_input.strip()
            except (EOFError, KeyboardInterrupt):
                print("\nBye!")
                break

            if not user_input:
                continue
            if user_input in ("/quit", "/exit"):
                print("Bye!")
                break
            if await self.commands.handle(user_input):
                # 路由切换后需要更新 client 并重探上游模型
                if self.client.route != self.config["route"]:
                    self.client = ChatClient(
                        base_url=self.config["base_url"],
                        route=self.config["route"],
                        api_key=self.config["api_key"],
                    )
                    self.commands.client = self.client
                    upstream, models = await self._probe_current_models()
                    self.available_models = models or []
                    self.display.print_models(models, upstream=upstream)
                # 更新补全词表（模型可能变了）
                session.completer = self._build_completer()
                continue

            self.conversation.add_user(user_input)

            try:
                if self.config["stream"]:
                    await self._stream_chat()
                else:
                    await self._sync_chat()
            except Exception as e:
                self.display.print_error(str(e))

    async def _sync_chat(self):
        """非流式对话。"""
        resp = await self.client.send(
            self.conversation.get_messages(), self.config["model"], stream=False
        )
        text, tool_calls = self.client.parse_response(resp)
        if tool_calls:
            for tc in tool_calls:
                name = tc.get("name") or tc.get("function", {}).get("name", "unknown")
                args = tc.get("input") or tc.get("arguments") or tc.get("function", {}).get("arguments", "{}")
                self.display.print_tool_call(name, args)
        if text:
            self.display.print_response(text)
        self.conversation.add_assistant(text, tool_calls)

    async def _stream_chat(self):
        """流式对话。"""
        self.display.print_stream_start()
        full_text = []
        async for data in self.client.send_stream(
            self.conversation.get_messages(), self.config["model"]
        ):
            chunk = self.client.parse_stream_chunk(data)
            if chunk:
                self.display.print_stream_chunk(chunk)
                full_text.append(chunk)
        self.display.print_stream_end()
        self.conversation.add_assistant("".join(full_text))


async def run_single(config: dict, message: str):
    """单次对话。"""
    client = ChatClient(
        base_url=config["base_url"],
        route=config["route"],
        api_key=config["api_key"],
    )
    display = Display()
    messages = [{"role": "user", "content": message}]

    try:
        if config["stream"]:
            display.print_stream_start()
            async for data in client.send_stream(messages, config["model"]):
                chunk = client.parse_stream_chunk(data)
                if chunk:
                    display.print_stream_chunk(chunk)
            display.print_stream_end()
        else:
            resp = await client.send(messages, config["model"], stream=False)
            text, _ = client.parse_response(resp)
            display.print_response(text)
    except Exception as e:
        display.print_error(str(e))


def start(args):
    """CLI chat 入口。"""
    from cli.config import load_client_config, merge_args

    config = load_client_config()
    config = merge_args(config, args)

    if args.message:
        asyncio.run(run_single(config, args.message))
    else:
        repl = Repl(config)
        asyncio.run(repl.run())
