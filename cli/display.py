"""终端格式化输出"""

from __future__ import annotations

import json

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.syntax import Syntax

console = Console()


class Display:
    """终端格式化输出，基于 rich。"""

    def print_welcome(self, base_url: str, route: str, model: str, stream: bool):
        info = f"服务: {base_url}\n路由: {route}  模型: {model}  流式: {'on' if stream else 'off'}"
        console.print(Panel(info, title="API Proxy CLI", border_style="cyan"))
        console.print("[dim]输入 /help 查看命令，/quit 退出[/dim]\n")

    def print_response(self, text: str):
        console.print()
        console.print(Markdown(text))
        console.print()

    def print_stream_start(self):
        console.print()

    def print_stream_chunk(self, text: str):
        console.print(text, end="", highlight=False)

    def print_stream_end(self):
        console.print("\n")

    def print_tool_call(self, name: str, arguments: dict | str):
        console.print(f"\n[yellow]Tool Call: {name}[/yellow]")
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                pass
        args_str = json.dumps(arguments, indent=2, ensure_ascii=False)
        console.print(Panel(
            Syntax(args_str, "json", theme="monokai"),
            title="arguments", border_style="yellow",
        ))

    def print_tool_result(self, result: str):
        console.print(Panel(result, title="result", border_style="green"))

    def print_error(self, message: str):
        console.print(f"[red]{message}[/red]")

    def print_info(self, message: str):
        console.print(f"[green]{message}[/green]")
