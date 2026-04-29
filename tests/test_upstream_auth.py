from __future__ import annotations


import httpx
import pytest
import respx

from app.config import get_settings
from app.upstream_auth import UpstreamUnreachable, verify_token


@pytest.fixture(autouse=True)
def _clear_cache():
    from app.upstream_auth import _CACHE

    _CACHE.clear()
    yield
    _CACHE.clear()


@respx.mock
async def test_valid_token_returns_true():
    url = get_settings().mcp_orchestrator_url
    respx.post(url).mock(return_value=httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {"tools": []}}))
    assert await verify_token("good-token") is True


@respx.mock
async def test_invalid_token_returns_false():
    url = get_settings().mcp_orchestrator_url
    respx.post(url).mock(return_value=httpx.Response(401, json={"error": "UNAUTHORIZED"}))
    assert await verify_token("bad-token") is False


@respx.mock
async def test_upstream_5xx_raises_unreachable():
    url = get_settings().mcp_orchestrator_url
    respx.post(url).mock(return_value=httpx.Response(503))
    with pytest.raises(UpstreamUnreachable):
        await verify_token("any-token")


@respx.mock
async def test_upstream_network_error_raises_unreachable():
    url = get_settings().mcp_orchestrator_url
    respx.post(url).mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(UpstreamUnreachable):
        await verify_token("any-token")


@respx.mock
async def test_cached_valid_does_not_recall():
    url = get_settings().mcp_orchestrator_url
    route = respx.post(url).mock(return_value=httpx.Response(200, json={"result": {}}))
    assert await verify_token("good-token") is True
    assert await verify_token("good-token") is True
    assert route.call_count == 1


@respx.mock
async def test_cached_invalid_does_not_recall():
    url = get_settings().mcp_orchestrator_url
    route = respx.post(url).mock(return_value=httpx.Response(401))
    assert await verify_token("bad-token") is False
    assert await verify_token("bad-token") is False
    assert route.call_count == 1


@respx.mock
async def test_cache_does_not_leak_between_tokens():
    url = get_settings().mcp_orchestrator_url
    respx.post(url).mock(side_effect=[
        httpx.Response(200, json={"result": {}}),
        httpx.Response(401),
    ])
    assert await verify_token("token-a") is True
    assert await verify_token("token-b") is False


@respx.mock
async def test_empty_token_returns_false_without_calling_upstream():
    url = get_settings().mcp_orchestrator_url
    route = respx.post(url).mock(return_value=httpx.Response(200))
    assert await verify_token("") is False
    assert await verify_token(None) is False  # type: ignore[arg-type]
    assert route.call_count == 0
