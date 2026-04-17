"""HTTP 探测工具 — 上游 /v1/models 模型列表探测 + 路由级结构化结果"""

from __future__ import annotations

import asyncio

from common.http import HttpClient


async def probe_models(base_url: str) -> list[str] | None:
    """探测 base_url 的可用模型，不支持或出错时返回 None。base_url 已含 /v1 时不重复拼接。"""
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


async def probe_route(name: str, conf: dict) -> dict:
    """探测单条路由配置，返回结构化结果字典。

    返回 {route, provider, base_url, status, status_reason, models}
      - status: "ok" | "failed" | "mockup"
      - status_reason: 失败时为 "探测失败" / "空列表"（fix5 会细化为 401/timeout 等）
      - models: 成功时为非空列表，否则 None
    """
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

    models = await probe_models(base_url)
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


async def probe_all(routes_conf: dict) -> list[dict]:
    """并发探测 routes_conf 中所有路由，保持配置顺序返回。"""
    names = list(routes_conf.keys())
    tasks = [probe_route(n, routes_conf[n]) for n in names]
    return await asyncio.gather(*tasks) if tasks else []
