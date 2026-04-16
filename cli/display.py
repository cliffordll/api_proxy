"""终端格式化输出"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

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

    def print_error(self, message: str):
        console.print(f"[red]✗ {message}[/red]")

    def print_info(self, message: str):
        console.print(f"[green]✓ {message}[/green]")
