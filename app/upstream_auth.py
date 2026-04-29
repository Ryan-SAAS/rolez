from __future__ import annotations

import hashlib
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)


class UpstreamAuthError(Exception):
    """Base error for upstream auth failures."""


class UpstreamUnreachable(UpstreamAuthError):
    """tech.saac was unreachable or returned 5xx — caller should respond 503."""


@dataclass(frozen=True, slots=True)
class _CacheEntry:
    valid: bool
    expires_at: float


# Bounded LRU cache. Without a cap, every distinct token (including brute-force
# probes) would create a permanent dict entry until process restart, giving
# any caller a path to OOM the service.
_CACHE_MAXSIZE = 10_000
_NEGATIVE_TTL_SECONDS = 5  # short — token revocation should propagate fast.
_CACHE: "OrderedDict[str, _CacheEntry]" = OrderedDict()


def _key(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _fingerprint(token: str) -> str:
    return _key(token)[:12]


def _cache_set(key: str, entry: _CacheEntry) -> None:
    _CACHE[key] = entry
    _CACHE.move_to_end(key)
    while len(_CACHE) > _CACHE_MAXSIZE:
        _CACHE.popitem(last=False)


def _cache_get(key: str, now: float) -> _CacheEntry | None:
    entry = _CACHE.get(key)
    if entry is None:
        return None
    if entry.expires_at <= now:
        _CACHE.pop(key, None)
        return None
    _CACHE.move_to_end(key)
    return entry


async def verify_token(token: str | None) -> bool:
    """Validate `token` against tech.saac via a cheap `tools/list` JSON-RPC probe.

    Returns True if the upstream accepts the token, False if it rejects.
    Raises ``UpstreamUnreachable`` if tech.saac is down or returns an
    unexpected status — callers should map this to 503.

    Cache is per-process and bounded (LRU, max ~10k entries). Positive results
    are cached for ``ROLEZ_AUTH_TTL_SECONDS`` (default 60s); negative results
    are cached for a shorter window (5s) so token revocation propagates fast.
    Empty/None tokens short-circuit to False without contacting upstream.
    """
    if not token:
        return False

    settings = get_settings()
    now = time.monotonic()
    key = _key(token)
    cached = _cache_get(key, now)
    if cached is not None:
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
        ttl = settings.rolez_auth_ttl_seconds
    elif resp.status_code in (401, 403):
        log.info(
            "upstream rejected token fp=%s status=%s",
            _fingerprint(token),
            resp.status_code,
        )
        valid = False
        ttl = _NEGATIVE_TTL_SECONDS
    else:
        raise UpstreamUnreachable(f"tech.saac returned unexpected status {resp.status_code}")

    _cache_set(key, _CacheEntry(valid=valid, expires_at=now + ttl))
    return valid
