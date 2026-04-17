"""models 子命令入口：按 routes 配置探测各上游可用模型并展示"""

from __future__ import annotations

import asyncio

from rich.console import Console
from rich.panel import Panel

from cli.core.config import load_client_config, load_routes
from cli.core.probe import probe_models


class Models:
    """models 子命令：探测并展示各路由上游可用模型。"""

    def __init__(
        self,
        route_filter: str | None = None,
        config_path: str = "config/settings.yaml",
    ):
        self.route_filter = route_filter
        self.config_path = config_path
        self.console = Console()

    async def run(self) -> None:
        results = await self._probe_all()
        server_url = load_client_config(self.config_path).get("base_url")
        self._render(results, server_url)

    async def _probe_all(self) -> list[dict]:
        """遍历 routes，返回 [{route, base_url, provider, models}]。"""
        routes = load_routes(self.config_path)
        if self.route_filter:
            routes = {k: v for k, v in routes.items() if k == self.route_filter}
        names = list(routes.keys())
        tasks = [probe_models(routes[n].get("base_url", "")) for n in names]
        probes = await asyncio.gather(*tasks) if tasks else []
        return [
            {
                "route": name,
                "base_url": routes[name].get("base_url", ""),
                "provider": routes[name].get("provider", ""),
                "models": models,
            }
            for name, models in zip(names, probes)
        ]

    def _render(self, results: list[dict], server_url: str | None) -> None:
        if not results:
            self.console.print("[dim]未找到路由配置[/dim]")
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
        self.console.print(
            Panel("\n\n".join(sections), title="Available Models", border_style="cyan")
        )


def start(args):
    """CLI models 入口。"""
    asyncio.run(Models(route_filter=getattr(args, "route", None)).run())
