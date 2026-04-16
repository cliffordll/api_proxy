"""CLI 客户端配置加载"""

from __future__ import annotations

from pathlib import Path

import yaml


DEFAULT_CLIENT_CONFIG = {
    "base_url": "http://localhost:8000",
    "route": "messages",
    "model": "claude-sonnet-4-6-20250514",
    "api_key": "",
    "stream": True,
}


def load_client_config(config_path: str = "config/settings.yaml") -> dict:
    """从 settings.yaml 的 client 段加载配置，合并默认值。"""
    config = {**DEFAULT_CLIENT_CONFIG}
    path = Path(config_path)
    if path.exists():
        with open(path, encoding="utf-8") as f:
            yaml_config = yaml.safe_load(f) or {}
        client_conf = yaml_config.get("client", {})
        if client_conf:
            config.update(client_conf)
    return config


def merge_args(config: dict, args) -> dict:
    """命令行参数覆盖配置文件。"""
    if getattr(args, "base_url", None):
        config["base_url"] = args.base_url
    if getattr(args, "route", None):
        config["route"] = args.route
    if getattr(args, "model", None):
        config["model"] = args.model
    if getattr(args, "api_key", None):
        config["api_key"] = args.api_key
    if getattr(args, "stream", None) is not None:
        config["stream"] = args.stream
    return config
