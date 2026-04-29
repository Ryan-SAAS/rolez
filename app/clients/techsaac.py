from __future__ import annotations

from typing import Any

import httpx


class TechsaacError(Exception):
    def __init__(self, message: str, status_code: int | None = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class TechsaacClient:
    """JSON-RPC over /api/mcp client matching @startanaicompany/techsaac-cli.

    Each call_tool() request uses the *caller's* tech.saac MCP token so the
    tech.saac side sees the assistant as the principal — rolez never elevates.
    """

    def __init__(self, base_url: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def call_tool(self, tool_name: str, arguments: dict, *, caller_token: str) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        headers = {
            "Authorization": f"ApiKey {caller_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "rolez/0.1 (+techsaac-client)",
        }
        async with httpx.AsyncClient(timeout=self.timeout) as http:
            try:
                resp = await http.post(self.base_url, json=payload, headers=headers)
            except httpx.HTTPError as e:
                raise TechsaacError(f"tech.saac unreachable: {e}") from e

        if resp.status_code != 200:
            raise TechsaacError(
                f"tech.saac returned HTTP {resp.status_code}",
                status_code=resp.status_code,
                body=_safe_body(resp),
            )

        try:
            data = resp.json()
        except ValueError as e:
            raise TechsaacError(f"tech.saac returned non-JSON body: {e}") from e

        if isinstance(data, dict) and "error" in data and data["error"] is not None:
            err = data["error"]
            msg = err.get("message", "tech.saac error") if isinstance(err, dict) else str(err)
            raise TechsaacError(msg, status_code=200, body=err)

        return data.get("result") if isinstance(data, dict) else data


def _safe_body(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except Exception:
        return resp.text
