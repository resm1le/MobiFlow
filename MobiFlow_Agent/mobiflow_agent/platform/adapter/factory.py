from __future__ import annotations

import os

from mobiflow_agent.platform.adapter.http import HttpPlatformAdapter
from mobiflow_agent.platform.adapter.mcp import McpPlatformAdapter
from mobiflow_agent.platform.adapter.protocol import PlatformAdapter


def create_platform_adapter(kind: str | None = None) -> PlatformAdapter:
    resolved_kind = (kind or os.environ.get("PLATFORM_ADAPTER_KIND") or "mcp").strip().casefold()
    if resolved_kind == "mcp":
        return McpPlatformAdapter()
    if resolved_kind == "http":
        return HttpPlatformAdapter()
    raise ValueError(f"Unsupported platform adapter kind: {resolved_kind}")


__all__ = ["create_platform_adapter"]
