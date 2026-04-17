"""服务配置"""

from __future__ import annotations

# 服务配置默认值
DEFAULT_SERVER_CONFIG = {
    "host": "0.0.0.0",
    "port": 8000,
    "log_level": "info",
    "default_max_tokens": 4096,
}

# 运行时配置（由 load_settings() 填充）
_server_config: dict = {}


def load_settings(server_conf: dict | None = None) -> None:
    """加载服务配置，合并默认值。"""
    _server_config.clear()
    _server_config.update(DEFAULT_SERVER_CONFIG)
    if server_conf:
        _server_config.update(server_conf)


def get_settings() -> dict:
    """获取服务配置。未初始化时返回默认值。"""
    if not _server_config:
        load_settings()
    return _server_config
