"""终端格式化输出"""

from __future__ import annotations

import json

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.syntax import Syntax

# legacy_windows=False 避免 GBK 代码页下 ✓/✗ 等 Unicode 符号编码失败
console = Console(legacy_windows=False)


class Display:
    """终端格式化输出，基于 rich。"""

    @staticmethod
    def _format_route_sections(
        results: list[dict],
        current: str | None = None,
        server_url: str | None = None,
    ) -> str:
        """格式化路由状态展示块（不含 Panel）。current 路由加黄色 *；mockup 用 server_url。"""
        lines = []
        for i, r in enumerate(results):
            if i > 0:
                lines.append("")
            head = f"[cyan]{r['route']}[/cyan]"
            provider = r.get("provider")
            if provider:
                head += f"  [dim]({provider})[/dim]"
            status = r["status"]
            if status == "ok":
                head += f"  [green]✓[/green]  [dim]{r['base_url']}[/dim]"
            elif status == "mockup":
                # 无真实上游，展示用户请求会打到的 server 地址
                head += f"  [green]✓[/green]  [dim]{server_url or r.get('base_url', '')}[/dim]"
            elif status == "failed":
                head += f"  [red]✗ {r.get('status_reason') or '探测失败'}[/red]"
            if r["route"] == current:
                head += "   [yellow]*[/yellow]"
            lines.append("  " + head)
            if status == "ok":
                for m in r.get("models") or []:
                    lines.append(f"    [dim]- {m}[/dim]")
            elif status == "mockup":
                lines.append("    [dim]- (mockup)[/dim]")
            else:
                lines.append("    [dim]- (无模型)[/dim]")
        return "\n".join(lines)

    def print_welcome(
        self,
        base_url: str,
        route: str,
        model: str,
        stream: bool,
        route_results: list[dict] | None = None,
        direct: bool = False,
    ):
        info = f"服务: {base_url}\n路由: {route}  模型: {model}  流式: {'on' if stream else 'off'}"
        if route_results:
            # 直连模式下只展示当前路由（所有 cache 条目共享同一端点，没必要重复）
            displayed = [r for r in route_results if r["route"] == route] if direct else route_results
            label = "直连端点:" if direct else "可用路由:"
            info += f"\n\n[dim]{label}[/dim]\n" + self._format_route_sections(
                displayed,
                current=None if direct else route,
                server_url=base_url,
            )
        console.print(Panel(info, title="API Proxy CLI", border_style="cyan"))
        console.print("[dim]输入 /help 查看命令，/quit 退出[/dim]\n")

    def print_route_status(self, result: dict):
        """单条路由切换后的探测结果展示。"""
        console.print()
        console.print("[dim]可用路由:[/dim]")
        console.print(self._format_route_sections([result]))
        console.print()

    def print_route_picker(
        self,
        routes_with_provider: list[tuple[str, str | None]],
        current: str | None = None,
    ) -> int | None:
        """显示路由数字选择器，等待用户输入。返回选中索引（0-based）或 None（跳过）。"""
        console.print()
        for i, (name, provider) in enumerate(routes_with_provider):
            marker = "   [yellow]*[/yellow]" if name == current else ""
            prov = f"  [dim]({provider})[/dim]" if provider else ""
            console.print(f"  [cyan]\\[{i + 1}][/cyan] {name}{prov}{marker}")
        try:
            choice = input("选择路由 (输入编号，回车跳过): ").strip()
        except (EOFError, KeyboardInterrupt):
            return None
        if not choice:
            return None
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(routes_with_provider):
                return idx
        except ValueError:
            pass
        return None

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

    def print_models(
        self,
        models: list[str] | None,
        numbered: bool = False,
        upstream: str | None = None,
        current: str | None = None,
    ):
        header = "可用模型" + (f" ({upstream})" if upstream else "")
        if models:
            console.print(f"[dim]{header}:[/dim]")
            for i, m in enumerate(models):
                marker = "   [yellow]*[/yellow]" if m == current else ""
                if numbered:
                    console.print(f"[dim]  [{i + 1}] {m}[/dim]{marker}")
                else:
                    console.print(f"[dim]  - {m}[/dim]{marker}")
        else:
            console.print(f"[dim]{header}: 探测不可用[/dim]")

    def print_error(self, message: str):
        console.print(f"[red]{message}[/red]")

    def print_info(self, message: str):
        console.print(f"[green]{message}[/green]")
