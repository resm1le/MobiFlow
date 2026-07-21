from __future__ import annotations

from mobiflow_agent.collection.protocol import CollectionDispatchPlatform
from mobiflow_agent.platform.adapter import HttpPlatformAdapter, McpPlatformAdapter


class _HttpTransport:
    def request_json(self, method, path, payload=None):
        raise AssertionError("not called")

    def download_bytes(self, path):
        raise AssertionError("not called")


class _McpTransport:
    def call(self, method, params=None):
        raise AssertionError("not called")


def test_real_adapters_implement_collection_dispatch_capability() -> None:
    assert isinstance(HttpPlatformAdapter(transport=_HttpTransport()), CollectionDispatchPlatform)
    assert isinstance(McpPlatformAdapter(transport=_McpTransport()), CollectionDispatchPlatform)
