from __future__ import annotations

from typing import Any

import httpx


class PluginzError(Exception):
    """Base error for pluginz client. Carries HTTP status + decoded body."""

    def __init__(self, message: str, status_code: int | None = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class PluginzNotFound(PluginzError):
    """The requested plugin does not exist upstream (404)."""


class PluginzUnreachable(PluginzError):
    """Network failure or 5xx — caller should treat as upstream outage."""


class PluginzClient:
    def __init__(self, base_url: str, token: str, timeout: float = 15.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
            "User-Agent": "rolez/0.3 (+pluginz-client)",
        }

    async def get_plugin(self, name: str) -> dict:
        url = f"{self.base_url}/api/v1/plugins/{name}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as http:
                resp = await http.get(url, headers=self._headers())
        except httpx.HTTPError as e:
            raise PluginzUnreachable(f"pluginz unreachable: {e}") from e
        if resp.status_code == 404:
            raise PluginzNotFound(f"plugin {name!r} not found upstream", status_code=404)
        if 400 <= resp.status_code < 500:
            raise PluginzError(
                f"pluginz returned {resp.status_code}: {resp.text}",
                status_code=resp.status_code,
                body=_safe_body(resp),
            )
        if resp.status_code >= 500:
            raise PluginzUnreachable(
                f"pluginz returned {resp.status_code}",
                status_code=resp.status_code,
                body=_safe_body(resp),
            )
        return resp.json()


def _safe_body(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except (ValueError, httpx.DecodingError):
        return resp.text
