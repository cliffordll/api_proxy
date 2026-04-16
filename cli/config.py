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


def load_client_config(config_path: str = "config/settings.yaml") -> dict:
    """从 settings.yaml 的 client 段加载配置，合并默认值。

    base_url 默认从 server 段的 host + port 推导。
    """
    config = {**DEFAULT_CLIENT_CONFIG}
    path = Path(config_path)
    if path.exists():
        with open(path, encoding="utf-8") as f:
            yaml_config = yaml.safe_load(f) or {}

        # 从 server 段推导默认 base_url
        server_conf = yaml_config.get("server", {})
        if server_conf:
            host = server_conf.get("host", "0.0.0.0")
            port = server_conf.get("port", 8000)
            # 0.0.0.0 对客户端来说应该用 localhost
            if host == "0.0.0.0":
                host = "localhost"
            config["base_url"] = f"http://{host}:{port}"

        # client 段覆盖
        client_conf = yaml_config.get("client", {})
        if client_conf:
            config.update(client_conf)
    return config


def merge_args(config: dict, args) -> dict:
    """命令行参数覆盖配置文件。"""
    if getattr(args, "base_url", None):
        url = args.base_url
        if url.rstrip("/").endswith("/v1"):
            from cli.display import Display
            Display().print_error(
                f"base-url 不需要带 /v1，已自动去除: {url} -> {url.rstrip('/').rsplit('/v1', 1)[0]}"
            )
            url = url.rstrip("/").rsplit("/v1", 1)[0]
        config["base_url"] = url
    if getattr(args, "route", None):
        config["route"] = args.route
    if getattr(args, "model", None):
        config["model"] = args.model
    if getattr(args, "api_key", None):
        config["api_key"] = args.api_key
    if getattr(args, "stream", None) is not None:
        config["stream"] = args.stream
    return config
