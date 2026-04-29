from __future__ import annotations


from app.auth import extract_apikey
from app.config import get_settings


def test_extract_apikey_handles_apikey_scheme():
    assert extract_apikey("ApiKey abc123") == "abc123"
    assert extract_apikey("apikey abc123") == "abc123"


def test_extract_apikey_handles_bearer_scheme():
    """Bearer is accepted as a courtesy — some clients only know Bearer."""
    assert extract_apikey("Bearer abc123") == "abc123"


def test_extract_apikey_returns_none_for_missing_or_malformed():
    assert extract_apikey(None) is None
    assert extract_apikey("") is None
    assert extract_apikey("garbage") is None


async def test_admin_apikey_constant_time_match():
    """Exercise the matcher directly — the FastAPI dependency wrapper is
    covered by the public/admin router tests."""
    from app.auth import _admin_apikey_matches

    settings = get_settings()
    assert _admin_apikey_matches(settings.rolez_admin_api_key) is True
    assert _admin_apikey_matches(settings.rolez_admin_api_key + "x") is False
    assert _admin_apikey_matches("") is False
    assert _admin_apikey_matches(None) is False
