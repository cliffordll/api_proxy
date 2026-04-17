"""交互式对话循环"""

from __future__ import annotations

import asyncio

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document

from cli.chat.commands import CommandHandler
from cli.chat.conversation import Conversation
from cli.core.client import ChatClient
from cli.core.config import load_routes
from cli.core.display import Display
from cli.core.probe import probe_all, probe_route
from common.routes import ROUTE_PRIORITY, ROUTES


COMMANDS = [
    "/help", "/model", "/models", "/route", "/routes",
    "/stream", "/history", "/clear", "/quit", "/exit",
]
STREAM_OPTIONS = ["on", "off"]


class DynamicCompleter(Completer):
    """根据输入上下文动态补全。"""

    def __init__(self, models: list[str] | None = None):
        self.models = models or []

    def get_completions(self, document: Document, complete_event):
        text = document.text_before_cursor
        words = text.split()

        if not text or text == "/":
            for cmd in COMMANDS:
                if cmd.startswith(text):
                    yield Completion(cmd, start_position=-len(text))
        elif len(words) == 1 and text.startswith("/"):
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

    def __init__(
        self,
        config: dict,
        route_results: list[dict] | None = None,
        footer_note: str | None = None,
    ):
        self.config = config
        self.client = ChatClient(
            base_url=config["base_url"],
            route=config["route"],
            api_key=config["api_key"],
        )
        self.conversation = Conversation()
        self.display = Display()
        self.commands = CommandHandler(config, self.conversation, self.display, self.client)
        self.route_results = route_results or []
        self.footer_note = footer_note
        self.available_models = _models_for_route(route_results or [], config["route"])

    def _build_completer(self) -> DynamicCompleter:
        return DynamicCompleter(models=self.available_models)

    async def _refresh_current_route(self):
        """/route 切换后：探测新路由，打印结果，更新 available_models 和默认 model。"""
        name = self.config["route"]
        if self.config.get("base_url_override"):
            conf = {"provider": "direct", "base_url": self.config["base_url"]}
        else:
            routes = load_routes()
            conf = routes.get(name, {})
        result = await probe_route(name, conf)
        replaced = False
        for i, r in enumerate(self.route_results):
            if r["route"] == name:
                self.route_results[i] = result
                replaced = True
                break
        if not replaced:
            self.route_results.append(result)
        self.available_models = result.get("models") or []
        # 未显式指定 --model 时，跟随新路由的首个模型
        if not self.config.get("model_override") and self.available_models:
            self.config["model"] = self.available_models[0]
        self.display.print_route_status(result)

    async def run(self):
        """主循环。"""
        self.display.print_welcome(
            self.config["base_url"],
            self.config["route"],
            self.config["model"],
            self.config["stream"],
            route_results=self.route_results,
            footer_note=self.footer_note,
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
                # 路由切换：更新 client，重探新路由
                if self.client.route != self.config["route"]:
                    self.client = ChatClient(
                        base_url=self.config["base_url"],
                        route=self.config["route"],
                        api_key=self.config["api_key"],
                    )
                    self.commands.client = self.client
                    await self._refresh_current_route()
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


def _models_for_route(results: list[dict], route: str) -> list[str]:
    """从 probe 结果里取指定路由的 models。"""
    for r in results:
        if r["route"] == route:
            return r.get("models") or []
    return []


async def _startup_probe(config: dict, args) -> tuple[list[dict], str | None]:
    """启动前路由决策 + 探测。

    返回 (route_results, footer_note)。同时回写 config["route"]。
    """
    explicit_base = config.get("base_url_override")

    if explicit_base:
        # 显式 --base-url：只探一条路由（默认 completions 或 args.route）
        if not getattr(args, "route", None):
            config["route"] = ROUTE_PRIORITY[0]
        route = config["route"]
        conf = {"provider": "direct", "base_url": config["base_url"]}
        result = await probe_route(route, conf)
        results = [result]
        _apply_default_model(config, results)
        return results, None

    # 默认模式：读 yaml（或 DEFAULT_MOCKUP_ROUTES 回退），并发探所有
    routes_conf = load_routes()
    results = await probe_all(routes_conf)
    if not getattr(args, "route", None):
        # 默认路由 = 配置第一条
        config["route"] = next(iter(routes_conf)) if routes_conf else ROUTE_PRIORITY[0]

    mockup_all = bool(results) and all(r["status"] == "mockup" for r in results)
    real_results = [r for r in results if r["status"] != "mockup"]
    all_failed = bool(real_results) and all(r["status"] == "failed" for r in real_results)

    footer_note = None
    if mockup_all:
        footer_note = "[mockup] 模式下响应正文开头会带 [mockup] 标记"
    elif all_failed:
        footer_note = f"[!] 所有路由探测失败，代理可能不可用。默认路由仍为 {config['route']}"

    _apply_default_model(config, results)
    return results, footer_note


def _apply_default_model(config: dict, results: list[dict]) -> None:
    """用户没传 --model 且当前路由探测到模型时，自动挑首个作为默认模型。"""
    if config.get("model_override"):
        return
    route = config.get("route")
    for r in results:
        if r["route"] == route and r.get("models"):
            config["model"] = r["models"][0]
            return


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
    from cli.core.config import load_client_config, merge_args

    config = load_client_config()
    config = merge_args(config, args)

    if args.message:
        # 单次对话：如果没指定 route，补一个默认
        if not config.get("route"):
            config["route"] = ROUTE_PRIORITY[0]
        asyncio.run(run_single(config, args.message))
        return

    # REPL：启动前决策 + 探测，结果喂给 Repl
    route_results, footer_note = asyncio.run(_startup_probe(config, args))
    repl = Repl(config, route_results=route_results, footer_note=footer_note)
    asyncio.run(repl.run())
