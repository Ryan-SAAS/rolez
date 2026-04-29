from __future__ import annotations

import hashlib
import hmac
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from app.config import Settings, get_settings


def token_fingerprint(token: str) -> str:
    """Short, non-reversible identifier for a token — safe to log."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]


def extract_apikey(authorization: str | None) -> str | None:
    """Pull the token out of an `Authorization: ApiKey <token>` header.

    Accepts both `ApiKey` (the scheme tech.saac uses) and `Bearer` for
    convenience. Returns None if the header is missing or malformed.
    """
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) != 2:
        return None
    scheme = parts[0].lower()
    if scheme not in ("apikey", "bearer"):
        return None
    return parts[1].strip() or None


def _admin_apikey_matches(token: str | None) -> bool:
    if not token:
        return False
    expected = get_settings().rolez_admin_api_key
    if not expected:
        return False
    return hmac.compare_digest(token, expected)


async def require_admin_apikey(
    authorization: Annotated[str | None, Header()] = None,
    _settings: Settings = Depends(get_settings),
) -> str:
    """FastAPI dependency: 401 unless the request carries the configured admin api key."""
    token = extract_apikey(authorization)
    if not _admin_apikey_matches(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid admin api key"
        )
    if token is None:  # `assert` would be stripped under -O / PYTHONOPTIMIZE.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing api key")
    return token
