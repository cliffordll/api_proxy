"""按 routes 配置探测各上游可用模型"""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import yaml


def load_routes(config_path: str = "config/settings.yaml") -> dict:
    """读 settings.yaml 的 routes 段。"""
    path = Path(config_path)
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("routes") or {}


def get_route_base_url(route: str, config_path: str = "config/settings.yaml") -> str | None:
    """返回 routes[route].base_url，找不到则返回 None。"""
    routes = load_routes(config_path)
    conf = routes.get(route)
    if not conf:
        return None
    return conf.get("base_url") or None


def _models_url(base_url: str) -> str:
    """根据 base_url 构造 /models 探测地址。base_url 已含 /v1 时不重复拼接。"""
    base = base_url.rstrip("/")
    if base.endswith("/v1"):
        return base + "/models"
    return base + "/v1/models"


async def probe_models(base_url: str) -> list[str] | None:
    """探测 base_url 的可用模型，不支持或出错时返回 None。"""
    url = _models_url(base_url)
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=5.0)
            if resp.status_code != 200:
                return None
            data = resp.json()
            items = data.get("data") or data.get("models") or []
            if not isinstance(items, list):
                return None
            return [m["id"] for m in items if isinstance(m, dict) and m.get("id")]
    except Exception:
        return None


async def list_all(
    route_filter: str | None = None,
    config_path: str = "config/settings.yaml",
) -> list[dict]:
    """遍历 routes，返回 [{route, base_url, provider, models}]。

    route_filter 非空时仅保留该路由。models 为 None 表示探测不可用。
    """
    routes = load_routes(config_path)
    if route_filter:
        routes = {k: v for k, v in routes.items() if k == route_filter}

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


def start(args):
    """CLI models 入口。"""
    from cli.config import load_client_config
    from cli.display import Display

    results = asyncio.run(list_all(route_filter=getattr(args, "route", None)))
    server_url = load_client_config().get("base_url")
    Display().print_route_models(results, server_url=server_url)
