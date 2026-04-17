"""路由探测 + chat 启动决策 + 默认模型挑选"""

from __future__ import annotations

import asyncio

from cli.core.config import load_routes
from common.http import HttpClient
from common.routes import ROUTE_PRIORITY


class Probe:
    """chat 启动时的路由探测 + 默认模型挑选。

    副作用：回写 `config["route"]`（未显式 `--route`）；回写 `config["model"]`（未显式 `--model`）。
    """

    def __init__(self, config: dict, args):
        self.config = config
        self.args = args

    async def run(self) -> list[dict]:
        """返回 route_results。"""
        if self.config.get("base_url_override"):
            results = await self._direct()
        else:
            results = await self._proxy()
        self._apply_default_model(results)
        return results

    async def _direct(self) -> list[dict]:
        """直连模式：所有协议共享同一 base_url，/v1/models 只探一次。"""
        if not getattr(self.args, "route", None):
            self.config["route"] = ROUTE_PRIORITY[0]
        base_url = self.config["base_url"]
        models = await self._probe_models(base_url)
        status = "ok" if models else "failed"
        reason = None if models else "探测失败"
        return [
            {
                "route": name,
                "provider": "direct",
                "base_url": base_url,
                "status": status,
                "status_reason": reason,
                "models": models if models else None,
            }
            for name in ROUTE_PRIORITY
        ]

    async def _proxy(self) -> list[dict]:
        """代理模式：并发探所有路由；默认 route = yaml 首条。"""
        routes_conf = load_routes()
        results = await self._probe_all(routes_conf)
        if not getattr(self.args, "route", None):
            self.config["route"] = next(iter(routes_conf)) if routes_conf else ROUTE_PRIORITY[0]
        return results

    def _apply_default_model(self, results: list[dict]) -> None:
        """未显式 --model 时，用当前路由的首个模型作为默认。"""
        if self.config.get("model_override"):
            return
        route = self.config.get("route")
        for r in results:
            if r["route"] == route and r.get("models"):
                self.config["model"] = r["models"][0]
                return

    async def _probe_all(self, routes_conf: dict) -> list[dict]:
        """并发探测 routes_conf 中所有路由，保持配置顺序返回。"""
        names = list(routes_conf.keys())
        tasks = [self._probe_route(n, routes_conf[n]) for n in names]
        return await asyncio.gather(*tasks) if tasks else []

    async def _probe_route(self, name: str, conf: dict) -> dict:
        """探测单条路由，返回结构化结果 {route, provider, base_url, status, status_reason, models}。"""
        provider = conf.get("provider")
        base_url = conf.get("base_url", "")
        result: dict = {
            "route": name,
            "provider": provider,
            "base_url": base_url,
            "status": None,
            "status_reason": None,
            "models": None,
        }
        if provider == "mockup":
            result["status"] = "mockup"
            return result
        models = await self._probe_models(base_url)
        if models is None:
            result["status"] = "failed"
            result["status_reason"] = "探测失败"
        elif not models:
            result["status"] = "failed"
            result["status_reason"] = "空列表"
        else:
            result["status"] = "ok"
            result["models"] = models
        return result

    async def _probe_models(self, base_url: str) -> list[str] | None:
        """探测 base_url 的可用模型；失败或空返回 None。base_url 已含 /v1 时不重复拼接。"""
        base = base_url.rstrip("/")
        if not base.endswith("/v1"):
            base += "/v1"
        http = HttpClient(base_url=base)
        data = await http.get_json("/models", swallow_errors=True)
        if data is None:
            return None
        items = data.get("data") or data.get("models") or []
        if not isinstance(items, list):
            return None
        return [m["id"] for m in items if isinstance(m, dict) and m.get("id")]
