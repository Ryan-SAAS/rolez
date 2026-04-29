from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass

import httpx

from app.config import get_settings


class UpstreamAuthError(Exception):
    """Base error for upstream auth failures."""


class UpstreamUnreachable(UpstreamAuthError):
    """tech.saac was unreachable or returned 5xx — caller should respond 503."""


@dataclass
class _CacheEntry:
    valid: bool
    expires_at: float


_CACHE: dict[str, _CacheEntry] = {}


def _key(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def verify_token(token: str | None) -> bool:
    """Validate `token` against tech.saac via a cheap `tools/list` JSON-RPC probe.

    Returns True if the upstream accepts the token, False if it rejects.
    Raises `UpstreamUnreachable` if tech.saac is down or returns an unexpected
    status — callers should map this to 503.

    Results are cached in-process for `ROLEZ_AUTH_TTL_SECONDS` keyed by
    `sha256(token)`. Empty/None tokens short-circuit to False without
    contacting upstream.
    """
    if not token:
        return False

    settings = get_settings()
    now = time.monotonic()
    key = _key(token)
    cached = _CACHE.get(key)
    if cached is not None and cached.expires_at > now:
        return cached.valid

    payload = {"jsonrpc": "2.0", "method": "tools/list", "id": 1}
    headers = {
        "Authorization": f"ApiKey {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as http:
            resp = await http.post(settings.mcp_orchestrator_url, json=payload, headers=headers)
    except httpx.HTTPError as e:
        raise UpstreamUnreachable(f"tech.saac unreachable: {e}") from e

    if resp.status_code == 200:
        valid = True
    elif resp.status_code in (401, 403):
        valid = False
    else:
        raise UpstreamUnreachable(f"tech.saac returned unexpected status {resp.status_code}")

    _CACHE[key] = _CacheEntry(valid=valid, expires_at=now + settings.rolez_auth_ttl_seconds)
    return valid
