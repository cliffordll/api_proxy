"""交互式对话循环"""

from __future__ import annotations

import asyncio

from prompt_toolkit import PromptSession

from cli.chat.commands import CommandHandler, DynamicCompleter
from cli.chat.conversation import Conversation
from cli.chat.probe import Probe
from cli.core.client import ChatClient
from cli.core.display import Display


class Repl:
    """交互式 REPL：装配 ChatClient + Conversation + CommandHandler + Display，驱动对话循环。"""

    def __init__(
        self,
        config: dict,
        route_results: list[dict] | None = None,
    ):
        self.config = config
        self.conversation = Conversation()
        self.display = Display()
        self.client = self._new_client()
        self.route_results = route_results or []
        self.commands = CommandHandler(
            config, self.conversation, self.display, self.client, self.route_results
        )

        def pick_models(route: str) -> list[str]:
            for r in self.route_results:
                if r["route"] == route:
                    return r.get("models") or []
            return []

        self.available_models = pick_models(config["route"])

    # ── 启动与主循环 ──────────────────────────────────────────

    async def run(self):
        self.display.print_welcome(
            self.config["base_url"],
            self.config["route"],
            self.config["model"],
            self.config["stream"],
            route_results=self.route_results,
            direct=bool(self.config.get("base_url_override")),
        )

        session = PromptSession(completer=self._build_completer())

        while True:
            user_input = await self._read_input(session)
            if user_input is None or user_input in ("/quit", "/exit"):
                print("Bye!")
                return
            if not user_input:
                continue

            if await self.commands.handle(user_input):
                self._post_command(session)
                continue

            self.conversation.add_user(user_input)
            self.display.print_context(self.config["route"], self.config["model"])
            try:
                await self._chat(self.config["stream"])
            except Exception as e:
                self.display.print_error(str(e))

    async def _read_input(self, session: PromptSession) -> str | None:
        """读一行用户输入；EOF/Ctrl-C 返回 None（退出信号）。"""
        try:
            text = await asyncio.get_event_loop().run_in_executor(
                None, lambda: session.prompt("> ")
            )
            return text.strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None

    def _post_command(self, session: PromptSession) -> None:
        """命令处理完后的统一后处理：路由切了就重建 client + 查缓存刷新 models；刷新补全词表。"""
        if self.client.route != self.config["route"]:
            self.client = self._new_client()
            self.commands.client = self.client
            self._apply_cached_route()
        session.completer = self._build_completer()

    def _apply_cached_route(self) -> None:
        """路由切换后：用启动探测缓存刷新 available_models；默认模型 = 新路由首个；展示状态。"""
        name = self.config["route"]
        result = next((r for r in self.route_results if r["route"] == name), None)
        self.available_models = (result and result.get("models")) or []
        if self.available_models:
            self.config["model"] = self.available_models[0]
        if result:
            self.display.print_route_status(result)

    # ── 装配 ──────────────────────────────────────────────────

    def _new_client(self) -> ChatClient:
        return ChatClient(
            base_url=self.config["base_url"],
            route=self.config["route"],
            api_key=self.config["api_key"],
        )

    def _build_completer(self) -> DynamicCompleter:
        return DynamicCompleter(models=self.available_models)

    # ── 聊天收发 ──────────────────────────────────────────────

    async def _chat(self, stream: bool) -> None:
        messages = self.conversation.get_messages()
        model = self.config["model"]
        if stream:
            await self._chat_stream(messages, model)
        else:
            await self._chat_sync(messages, model)

    async def _chat_sync(self, messages: list[dict], model: str) -> None:
        resp = await self.client.send(messages, model, stream=False)
        text, tool_calls = self.client.parse_response(resp)
        if tool_calls:
            for tc in tool_calls:
                name = tc.get("name") or tc.get("function", {}).get("name", "unknown")
                args = tc.get("input") or tc.get("arguments") or tc.get("function", {}).get("arguments", "{}")
                self.display.print_tool_call(name, args)
        if text:
            self.display.print_response(text)
        self.conversation.add_assistant(text, tool_calls)

    async def _chat_stream(self, messages: list[dict], model: str) -> None:
        self.display.print_stream_start()
        full_text: list[str] = []
        async for data in self.client.send_stream(messages, model):
            chunk = self.client.parse_stream_chunk(data)
            if chunk:
                self.display.print_stream_chunk(chunk)
                full_text.append(chunk)
        self.display.print_stream_end()
        self.conversation.add_assistant("".join(full_text))


def start(args) -> None:
    """CLI `chat` 入口。"""
    from cli.core.config import load_client_config, merge_args

    config = merge_args(load_client_config(), args)
    route_results = asyncio.run(Probe(config, args).run())
    asyncio.run(Repl(config, route_results=route_results).run())
