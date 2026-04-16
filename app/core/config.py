"""服务配置 + 模型映射"""

from __future__ import annotations

# 服务配置默认值
DEFAULT_SERVER_CONFIG = {
    "host": "0.0.0.0",
    "port": 8000,
    "log_level": "info",
    "default_max_tokens": 4096,
}

# 默认模型映射
DEFAULT_MAPPINGS = {
    "openai_to_claude": {
        "gpt-4o": "claude-sonnet-4-6-20250514",
        "gpt-4-turbo": "claude-sonnet-4-6-20250514",
        "gpt-4": "claude-opus-4-6-20250514",
        "gpt-3.5-turbo": "claude-haiku-4-5-20251001",
    },
    "claude_to_openai": {
        "claude-opus-4-6-20250514": "gpt-4",
        "claude-sonnet-4-6-20250514": "gpt-4o",
        "claude-haiku-4-5-20251001": "gpt-3.5-turbo",
    },
}

# 运行时配置（由 load_settings() 填充）
_server_config: dict = {}
_mappings: dict = {}


def load_settings(server_conf: dict | None = None, mappings_conf: dict | None = None) -> None:
    """加载服务配置和模型映射，合并默认值。"""
    _server_config.clear()
    _server_config.update(DEFAULT_SERVER_CONFIG)
    if server_conf:
        _server_config.update(server_conf)

    _mappings.clear()
    for direction in ("openai_to_claude", "claude_to_openai"):
        _mappings[direction] = {**DEFAULT_MAPPINGS[direction]}
        if mappings_conf and direction in mappings_conf:
            _mappings[direction].update(mappings_conf[direction])


def get_settings() -> dict:
    """获取服务配置。未初始化时返回默认值。"""
    if not _server_config:
        load_settings()
    return _server_config


def map_model(model: str, direction: str) -> str:
    """映射模型名，未命中则透传。"""
    if not _mappings:
        load_settings()
    return _mappings.get(direction, {}).get(model, model)
