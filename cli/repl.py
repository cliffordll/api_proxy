"""交互式对话循环"""

from __future__ import annotations

import asyncio

from cli.client import ChatClient
from cli.commands import CommandHandler
from cli.conversation import Conversation
from cli.display import Display


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
        self.commands = CommandHandler(config, self.conversation, self.display)

    async def run(self):
        """主循环。"""
        self.display.print_welcome(
            self.config["base_url"],
            self.config["route"],
            self.config["model"],
            self.config["stream"],
        )

        while True:
            try:
                user_input = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nBye!")
                break

            if not user_input:
                continue
            if user_input in ("/quit", "/exit"):
                print("Bye!")
                break
            if self.commands.handle(user_input):
                # 路由切换后需要更新 client
                if self.client.route != self.config["route"]:
                    self.client = ChatClient(
                        base_url=self.config["base_url"],
                        route=self.config["route"],
                        api_key=self.config["api_key"],
                    )
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
