"""配置加载 + Proxy 自动装配"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.core.config import load_settings
from app.core.proxy import Proxy, registry


# 供应商工厂：provider 名 → Client 类（延迟导入，避免循环依赖）
def _get_provider_registry() -> dict[str, type]:
    from app.clients.claude_client import ClaudeClient
    from app.clients.httpx_client import HttpxClient
    from app.clients.mockup_client import MockupClient
    from app.clients.openai_client import OpenAIClient

    return {
        "claude": ClaudeClient,
        "openai": OpenAIClient,
        "ollama": OpenAIClient,    # 兼容 OpenAI 协议
        "httpx":  HttpxClient,
        "mockup": MockupClient,
    }


# 转换器工厂：converter 名 → Converter 类（延迟导入）
def _get_converter_registry() -> dict[str, type]:
    from app.converters.completions_from_messages import CompletionsFromMessagesConverter
    from app.converters.completions_from_responses import CompletionsFromResponsesConverter
    from app.converters.messages_from_completions import MessagesFromCompletionsConverter
    from app.converters.messages_from_responses import MessagesFromResponsesConverter
    from app.converters.responses_from_completions import ResponsesFromCompletionsConverter
    from app.converters.responses_from_messages import ResponsesFromMessagesConverter

    return {
        "completions_from_messages":  CompletionsFromMessagesConverter,
        "completions_from_responses": CompletionsFromResponsesConverter,
        "messages_from_completions":  MessagesFromCompletionsConverter,
        "messages_from_responses":    MessagesFromResponsesConverter,
        "responses_from_messages":    ResponsesFromMessagesConverter,
        "responses_from_completions": ResponsesFromCompletionsConverter,
    }


# 内置默认配置（config/settings.yaml 不存在时使用）
DEFAULT_CONFIG: dict[str, Any] = {
    "completions": {
        "path": "/v1/chat/completions",
        "base_url": "https://api.anthropic.com",
        "provider": "claude",
        "from": "messages",
    },
    "responses": {
        "path": "/v1/responses",
        "base_url": "https://api.anthropic.com",
        "provider": "claude",
        "from": "messages",
    },
    "messages": {
        "path": "/v1/messages",
        "base_url": "https://api.openai.com/v1",
        "provider": "openai",
        "from": "completions",
    },
}


def load_providers(config_path: str = "config/settings.yaml") -> None:
    """从 YAML 加载配置，初始化服务配置 + 自动装配 Proxy。

    YAML 中 server 段为服务配置，其余段为 Provider 配置。
    配置文件不存在时使用内置默认配置。
    """
    path = Path(config_path)
    if path.exists():
        with open(path, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
    else:
        config = DEFAULT_CONFIG.copy()

    # 分离各段配置
    server_conf = config.pop("server", None)
    mappings_conf = config.pop("mappings", None)
    config.pop("client", None)  # client 段由 CLI 读取，loader 不处理
    load_settings(server_conf, mappings_conf)

    # 提取 routes 段，兼容新旧格式
    routes_conf = config.pop("routes", None)
    if routes_conf:
        config = routes_conf
    # 无路由配置时使用默认
    if not config:
        config = DEFAULT_CONFIG

    provider_registry = _get_provider_registry()
    converter_registry = _get_converter_registry()

    for name, conf in config.items():
        provider_name = conf["provider"]
        from_interface = conf.get("from")

        if provider_name not in provider_registry:
            raise ValueError(
                f"Unknown provider '{provider_name}'. "
                f"Available: {list(provider_registry.keys())}"
            )

        client_cls = provider_registry[provider_name]

        if from_interface and from_interface != name:
            # 从路由名 + from 推导 converter: {name}_from_{from}
            converter_name = f"{name}_from_{from_interface}"
            if converter_name not in converter_registry:
                raise ValueError(
                    f"Unknown converter '{converter_name}' "
                    f"(derived from route '{name}' + from '{from_interface}'). "
                    f"Available: {list(converter_registry.keys())}"
                )
            converter_cls = converter_registry[converter_name]
            interface = from_interface
        else:
            # 无 from → 透传，interface 默认等于路由名
            from app.converters.passthrough import PassthroughConverter
            converter_cls = PassthroughConverter
            interface = name

        client = client_cls(
            base_url=conf["base_url"],
            interface=interface,
        )
        converter = converter_cls()

        registry.add(name, Proxy(client=client, converter=converter))
