"""Registry 单元测试"""

import pytest
from app.core.client import BaseClient
from app.core.converter import BaseConverter
from app.core.registry import ProviderRegistry, ProviderEntry


class FakeClient(BaseClient):
    async def send(self, params: dict, api_key: str, stream: bool = False):
        return {}


class FakeConverter(BaseConverter):
    def convert_request(self, request: dict) -> dict:
        return request

    def convert_response(self, response) -> dict:
        return {}

    def convert_stream_event(self, event, state: dict) -> list:
        return []


class TestProviderRegistry:
    def test_register_and_get(self):
        reg = ProviderRegistry()
        entry = ProviderEntry(
            client=FakeClient(),
            request_converter=FakeConverter(),
            response_converter=FakeConverter(),
        )
        reg.register("test", entry)
        assert reg.get("test") is entry

    def test_get_not_registered_raises(self):
        reg = ProviderRegistry()
        with pytest.raises(KeyError, match="not registered"):
            reg.get("nonexistent")

    def test_list_providers_empty(self):
        reg = ProviderRegistry()
        assert reg.list_providers() == []

    def test_list_providers(self):
        reg = ProviderRegistry()
        entry = ProviderEntry(
            client=FakeClient(),
            request_converter=FakeConverter(),
            response_converter=FakeConverter(),
        )
        reg.register("a", entry)
        reg.register("b", entry)
        assert sorted(reg.list_providers()) == ["a", "b"]

    def test_register_overwrite(self):
        reg = ProviderRegistry()
        entry1 = ProviderEntry(
            client=FakeClient(),
            request_converter=FakeConverter(),
            response_converter=FakeConverter(),
        )
        entry2 = ProviderEntry(
            client=FakeClient(),
            request_converter=FakeConverter(),
            response_converter=FakeConverter(),
        )
        reg.register("x", entry1)
        reg.register("x", entry2)
        assert reg.get("x") is entry2

    def test_fake_client_matches_protocol(self):
        assert isinstance(FakeClient(), BaseClient)

    def test_fake_converter_matches_protocol(self):
        assert isinstance(FakeConverter(), BaseConverter)
