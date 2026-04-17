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

    def print_welcome(
        self,
        base_url: str,
        route: str,
        model: str,
        stream: bool,
        models: list[str] | None = None,
        upstream: str | None = None,
    ):
        info = f"服务: {base_url}\n路由: {route}  模型: {model}  流式: {'on' if stream else 'off'}"
        header = "可用模型" + (f" ({upstream})" if upstream else "")
        if models:
            info += f"\n\n[dim]{header}:[/dim]\n" + "\n".join(f"[dim]  - {m}[/dim]" for m in models)
        else:
            info += f"\n\n[dim]{header}: 探测不可用[/dim]"
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

    def print_models(self, models: list[str] | None, numbered: bool = False, upstream: str | None = None):
        header = "可用模型" + (f" ({upstream})" if upstream else "")
        if models:
            console.print(f"[dim]{header}:[/dim]")
            for i, m in enumerate(models):
                if numbered:
                    console.print(f"[dim]  [{i + 1}] {m}[/dim]")
                else:
                    console.print(f"[dim]  - {m}[/dim]")
        else:
            console.print(f"[dim]{header}: 探测不可用[/dim]")

    def print_route_models(self, results: list[dict], server_url: str | None = None):
        """按路由分组展示模型列表。results 来自 cli.models.list_all。"""
        if not results:
            console.print("[dim]未找到路由配置[/dim]")
            return
        sections = []
        if server_url:
            sections.append(f"服务: {server_url}")
        for item in results:
            head = f"[cyan]{item['route']}[/cyan] [dim]({item['base_url']} / {item['provider']})[/dim]"
            models = item["models"]
            if models is None:
                body = "[dim]  模型探测不可用[/dim]"
            elif not models:
                body = "[dim]  (无模型)[/dim]"
            else:
                body = "\n".join(f"[dim]  - {m}[/dim]" for m in models)
            sections.append(f"{head}\n{body}")
        console.print(Panel("\n\n".join(sections), title="Available Models", border_style="cyan"))

    def print_error(self, message: str):
        console.print(f"[red]{message}[/red]")

    def print_info(self, message: str):
        console.print(f"[green]{message}[/green]")
