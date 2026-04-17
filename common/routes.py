"""API 协议常量 — 路由名、URL 路径、优先级、默认配置、认证头格式。

三种协议：
  - completions (OpenAI 风格): /v1/chat/completions, `Authorization: Bearer <key>`
  - responses   (OpenAI 风格): /v1/responses,        `Authorization: Bearer <key>`
  - messages    (Claude 风格):  /v1/messages,         `x-api-key: <key>` + anthropic-version
"""

from __future__ import annotations


ROUTE_PATHS: dict[str, str] = {
    "completions": "/v1/chat/completions",
    "messages": "/v1/messages",
    "responses": "/v1/responses",
}

ROUTES: list[str] = list(ROUTE_PATHS.keys())

# 固定优先级（用于没有 yaml 时的展示顺序、显式 --base-url 场景 /routes picker 等）
ROUTE_PRIORITY: list[str] = ["completions", "responses", "messages"]

# 默认路由配置：settings.yaml 缺失或某条标准路由未配置时回退到此
# 三条全走 mockup，base_url 是占位符（mockup 不发起实际 HTTP 请求）
DEFAULT_MOCKUP_ROUTES: dict[str, dict] = {
    "completions": {"path": "/v1/chat/completions", "base_url": "http://localhost", "provider": "mockup"},
    "responses":   {"path": "/v1/responses",        "base_url": "http://localhost", "provider": "mockup"},
    "messages":    {"path": "/v1/messages",         "base_url": "http://localhost", "provider": "mockup"},
}


def merge_routes(yaml_routes: dict | None) -> dict:
    """合并 yaml 配置和默认 mockup 路由：yaml 有的用 yaml，缺的标准路由回落到 mockup。"""
    merged = {**DEFAULT_MOCKUP_ROUTES}
    if yaml_routes:
        merged.update(yaml_routes)
    return merged


def auth_headers(route: str, api_key: str) -> dict[str, str]:
    """根据路由返回上游认证头（含 Content-Type）。"""
    headers = {"Content-Type": "application/json"}
    if route == "messages":
        headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
    else:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers
