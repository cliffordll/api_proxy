"""HTTP 探测工具 — 当前仅用于上游 /v1/models 模型列表探测"""

from __future__ import annotations

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
