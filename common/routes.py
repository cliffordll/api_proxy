"""API 协议常量 — 路由名、URL 路径、认证头格式。

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


def auth_headers(route: str, api_key: str) -> dict[str, str]:
    """根据路由返回上游认证头（含 Content-Type）。"""
    headers = {"Content-Type": "application/json"}
    if route == "messages":
        headers["x-api-key"] = api_key
        headers["anthropic-version"] = "2023-06-01"
    else:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers
