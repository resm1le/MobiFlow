from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol
from urllib import error, request

from mobiflow_agent.platform.adapter.protocol import PlatformAdapterError

PROTOCOL_VERSION = "tool-envelope-v2"
DEFAULT_TIMEOUT_SECONDS = 15.0


class ToolRuntimeTransport(Protocol):
    def request_json(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Send a JSON request and decode the JSON response."""

    def download_bytes(self, path: str) -> bytes:
        """Download binary content from the tool runtime."""


@dataclass(slots=True)
class UrlLibToolRuntimeTransport:
    base_url: str
    bearer_token: str | None = None
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS

    def request_json(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        req = request.Request(self._url(path), data=body, headers=headers, method=method.upper())
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                content = response.read().decode("utf-8")
        except error.HTTPError as exc:
            content = exc.read().decode("utf-8", errors="replace")
            raise PlatformAdapterError("HTTP_ERROR", content or f"http_{exc.code}", retryable=exc.code >= 500) from exc
        except OSError as exc:
            raise PlatformAdapterError("TRANSPORT_ERROR", str(exc), retryable=True) from exc
        return json.loads(content) if content else {}

    def download_bytes(self, path: str) -> bytes:
        headers = {}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        req = request.Request(self._url(path), headers=headers, method="GET")
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                return response.read()
        except error.HTTPError as exc:
            raise PlatformAdapterError("HTTP_ERROR", f"http_{exc.code}", retryable=exc.code >= 500) from exc
        except OSError as exc:
            raise PlatformAdapterError("TRANSPORT_ERROR", str(exc), retryable=True) from exc

    def _url(self, path: str) -> str:
        base = self.base_url.rstrip("/")
        suffix = path if path.startswith("/") else f"/{path}"
        return f"{base}{suffix}"


__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "PROTOCOL_VERSION",
    "ToolRuntimeTransport",
    "UrlLibToolRuntimeTransport",
]
