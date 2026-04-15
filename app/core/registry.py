"""Provider 注册表：管理客户端和转换器的组合"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.protocols import BaseClient, BaseConverter


@dataclass
class ProviderEntry:
    """Provider 注册条目"""

    client: BaseClient
    request_converter: BaseConverter
    response_converter: BaseConverter


class ProviderRegistry:
    """Provider 注册表，集中管理所有 Provider 的客户端和转换器。"""

    def __init__(self) -> None:
        self._providers: dict[str, ProviderEntry] = {}

    def register(self, name: str, entry: ProviderEntry) -> None:
        """注册一个 Provider。"""
        self._providers[name] = entry

    def get(self, name: str) -> ProviderEntry:
        """获取指定 Provider，不存在时抛出 KeyError。"""
        if name not in self._providers:
            raise KeyError(f"Provider '{name}' not registered. Available: {self.list_providers()}")
        return self._providers[name]

    def list_providers(self) -> list[str]:
        """列出所有已注册的 Provider 名称。"""
        return list(self._providers.keys())


# 全局注册表实例
registry = ProviderRegistry()
