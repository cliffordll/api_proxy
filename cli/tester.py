"""冒烟测试 — 自动验证服务可用性"""

from __future__ import annotations

import asyncio
import json

import httpx

from cli.core.display import Display


class Tester:
    """冒烟测试，验证服务各端点是否正常。"""

    def __init__(self, base_url: str, api_key: str = "test-key"):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.display = Display()
        self.passed = 0
        self.failed = 0

    async def run(self, route: str | None = None) -> bool:
        """运行测试。指定 route 测单个，否则测全部。"""
        from rich.console import Console
        Console().print("\n[bold]API Proxy 冒烟测试[/bold]")
        Console().print("=" * 40)

        await self._test("GET", "/health", None, None)

        routes = [route] if route else ["completions", "messages", "responses"]
        for r in routes:
            await self._test_route(r, stream=False)
            await self._test_route(r, stream=True)

        total = self.passed + self.failed
        from rich.console import Console
        Console().print(f"\n{self.passed}/{total} 通过\n")
        return self.failed == 0

    async def _test_route(self, route: str, stream: bool):
        """测试单个路由。"""
        path_map = {
            "completions": "/v1/chat/completions",
            "messages": "/v1/messages",
            "responses": "/v1/responses",
        }
        path = path_map[route]
        method = "POST"
        mode = "流式" if stream else "非流式"
        label = f"{path} ({mode})"

        # 构建请求
        if route == "responses":
            body = {"model": "test", "input": "hi", "stream": stream}
        else:
            body = {"model": "test", "messages": [{"role": "user", "content": "hi"}], "stream": stream}
            if route == "messages":
                body["max_tokens"] = 50

        # 认证头
        if route == "messages":
            headers = {"x-api-key": self.api_key, "Content-Type": "application/json"}
        else:
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

        await self._test(method, path, body, headers, label=label, stream=stream)

    async def _test(self, method: str, path: str, body: dict | None,
                    headers: dict | None, label: str | None = None, stream: bool = False):
        """执行单个测试。"""
        url = self.base_url + path
        label = label or f"{method} {path}"

        try:
            async with httpx.AsyncClient() as client:
                if not stream:
                    if method == "GET":
                        resp = await client.get(url, timeout=10.0)
                    else:
                        resp = await client.post(url, json=body, headers=headers, timeout=30.0)
                    status = resp.status_code
                    if status == 200:
                        self._pass(label, f"{status}")
                    else:
                        self._fail(label, f"{status}")
                else:
                    async with client.stream(method, url, json=body, headers=headers, timeout=30.0) as resp:
                        status = resp.status_code
                        chunks = 0
                        async for line in resp.aiter_lines():
                            if line.strip().startswith("data:"):
                                chunks += 1
                        if status == 200 and chunks > 0:
                            self._pass(label, f"{status} SSE ({chunks} chunks)")
                        else:
                            self._fail(label, f"{status} ({chunks} chunks)")
        except Exception as e:
            self._fail(label, str(e))

    def _pass(self, label: str, detail: str):
        self.passed += 1
        from rich.console import Console
        Console().print(f"[green]PASS[/green] {label:45s} {detail}")

    def _fail(self, label: str, detail: str):
        self.failed += 1
        from rich.console import Console
        Console().print(f"[red]FAIL[/red] {label:45s} {detail}")


def start(args):
    """CLI test 入口。"""
    from cli.core.config import load_client_config, merge_args

    config = load_client_config()
    config = merge_args(config, args)

    tester = Tester(
        base_url=config["base_url"],
        api_key=config.get("api_key", "test-key"),
    )
    route = getattr(args, "route", None)
    success = asyncio.run(tester.run(route))
    if not success:
        import sys
        sys.exit(1)
