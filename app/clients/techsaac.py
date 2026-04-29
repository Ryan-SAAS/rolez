from __future__ import annotations

import json
import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)


class TechsaacError(Exception):
    """Base for tech.saac client errors. Concrete subclasses below let callers
    isinstance-route by failure mode instead of inspecting status_code."""

    def __init__(self, message: str, status_code: int | None = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class TechsaacUnreachable(TechsaacError):
    """Network failure — no HTTP response received. Map to 503 upstream."""


class TechsaacHTTPError(TechsaacError):
    """tech.saac returned a non-2xx HTTP status. status_code is set."""


class TechsaacRPCError(TechsaacError):
    """tech.saac returned 200 with a JSON-RPC `error` member. The transport
    succeeded; the tool call failed. Map to 502 — we cannot trust the
    upstream's intended status code (it is hidden inside the JSON-RPC envelope)."""


class TechsaacProtocolError(TechsaacError):
    """tech.saac returned 200 with a body we cannot parse as JSON — protocol
    drift. Map to 502."""


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
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as http:
                resp = await http.post(self.base_url, json=payload, headers=headers)
        except httpx.HTTPError as e:
            raise TechsaacUnreachable(f"tech.saac unreachable: {e}") from e

        if resp.status_code != 200:
            raise TechsaacHTTPError(
                f"tech.saac returned HTTP {resp.status_code}",
                status_code=resp.status_code,
                body=_safe_body(resp),
            )

        try:
            data = resp.json()
        except (ValueError, json.JSONDecodeError) as e:
            raise TechsaacProtocolError(
                f"tech.saac returned non-JSON body: {e}",
                status_code=200,
                body=resp.text,
            ) from e

        if isinstance(data, dict) and data.get("error") is not None:
            err = data["error"]
            msg = err.get("message", "tech.saac error") if isinstance(err, dict) else str(err)
            raise TechsaacRPCError(msg, status_code=200, body=err)

        return data.get("result") if isinstance(data, dict) else data


def _safe_body(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except (ValueError, json.JSONDecodeError, httpx.DecodingError):
        return resp.text
