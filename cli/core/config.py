"""CLI 客户端配置加载"""

from __future__ import annotations

from pathlib import Path

import yaml


DEFAULT_CLIENT_CONFIG = {
    "base_url": "http://localhost:8000",
    "route": "completions",
    "model": "claude-sonnet-4-6-20250514",
    "api_key": "EMPTY",
    "stream": True,
}


def load_routes(config_path: str = "config/settings.yaml") -> dict:
    """读 settings.yaml 的 routes 段；缺失的标准路由回落到 DEFAULT_MOCKUP_ROUTES。"""
    from common.routes import merge_routes

    path = Path(config_path)
    yaml_routes: dict | None = None
    if path.exists():
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        yaml_routes = data.get("routes")
    return merge_routes(yaml_routes)


def get_route_base_url(route: str, config_path: str = "config/settings.yaml") -> str | None:
    """返回 routes[route].base_url，找不到则返回 None。"""
    conf = load_routes(config_path).get(route)
    return conf.get("base_url") if conf else None


def load_client_config(config_path: str = "config/settings.yaml") -> dict:
    """从 settings.yaml 推导 CLI 默认值。base_url 从 server 段 host + port 推导。"""
    config = {**DEFAULT_CLIENT_CONFIG}
    path = Path(config_path)
    if not path.exists():
        return config

    with open(path, encoding="utf-8") as f:
        yaml_config = yaml.safe_load(f) or {}

    server_conf = yaml_config.get("server") or {}
    host = server_conf.get("host", "0.0.0.0")
    port = server_conf.get("port", 8000)
    if host == "0.0.0.0":
        host = "localhost"
    config["base_url"] = f"http://{host}:{port}"

    return config


def merge_args(config: dict, args) -> dict:
    """命令行参数覆盖配置文件。"""
    if getattr(args, "base_url", None):
        url = args.base_url
        if url.rstrip("/").endswith("/v1"):
            from cli.core.display import Display
            Display().print_error(
                f"base-url 不需要带 /v1，已自动去除: {url} -> {url.rstrip('/').rsplit('/v1', 1)[0]}"
            )
            url = url.rstrip("/").rsplit("/v1", 1)[0]
        config["base_url"] = url
        config["base_url_override"] = True
    if getattr(args, "route", None):
        config["route"] = args.route
    if getattr(args, "model", None):
        config["model"] = args.model
        config["model_override"] = True
    if getattr(args, "api_key", None):
        config["api_key"] = args.api_key
    if getattr(args, "stream", None) is not None:
        config["stream"] = args.stream
    return config
