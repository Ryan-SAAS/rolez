"""Fixtures for live integration / contract tests.

These tests hit real external services (skillz, agentz, tech.saac) to
detect upstream contract drift early. Each test is gated on the relevant
token being present in the environment — missing env vars cause skips,
not failures, so partial credentials still give partial signal.

The tests are deliberately **sync** (not pytest-asyncio): contract
tests don't need concurrency, and pytest-asyncio's loop interacts
poorly with httpx's network layer in some environments (notably WSL2,
where DNS lookups inside the auto loop fail with EAI_NONAME). For the
async ``SkillzClient`` / ``AgentzClient`` / ``TechsaacClient`` the
tests wrap calls in ``asyncio.run()`` — same code path, fresh loop per
test.

Run with::

    pytest -m integration

CI should run these on a schedule (e.g. nightly) or on PRs that touch
``app/clients/`` or ``app/provisioner.py``.
"""
from __future__ import annotations

import asyncio
import os
from typing import Awaitable, TypeVar

import httpx
import pytest

SKILLZ_API_URL_DEFAULT = "https://skillz.startanaicompany.com"
AGENTZ_API_URL_DEFAULT = "https://agentz.startanaicompany.com"
TECHSAAC_MCP_URL_DEFAULT = "https://tech.startanaicompany.com/api/mcp"

T = TypeVar("T")


def _env_or_skip(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        pytest.skip(f"{name} not set — skipping live integration test")
    return val


@pytest.fixture
def skillz_token() -> str:
    return _env_or_skip("SKILLZ_TOKEN")


@pytest.fixture
def agentz_token() -> str:
    return _env_or_skip("AGENTZ_TOKEN")


@pytest.fixture
def mcp_token() -> str:
    return _env_or_skip("MCP_ORCHESTRATOR_API_KEY")


@pytest.fixture
def skillz_url() -> str:
    return os.environ.get("SKILLZ_API_URL", SKILLZ_API_URL_DEFAULT)


@pytest.fixture
def agentz_url() -> str:
    return os.environ.get("AGENTZ_API_URL", AGENTZ_API_URL_DEFAULT)


@pytest.fixture
def mcp_url() -> str:
    return os.environ.get("MCP_ORCHESTRATOR_URL", TECHSAAC_MCP_URL_DEFAULT)


@pytest.fixture
def http_timeout() -> float:
    return float(os.environ.get("INTEGRATION_HTTP_TIMEOUT", "15"))


def run(coro: Awaitable[T]) -> T:
    """Drive an async coroutine to completion in a fresh event loop —
    sidesteps pytest-asyncio's session loop, which causes httpx to
    fail DNS lookups in some environments (WSL2)."""
    return asyncio.run(coro)  # type: ignore[arg-type]


def call_mcp(
    *, url: str, token: str, method: str, params: dict | None = None, timeout: float = 15.0,
) -> dict:
    """Tiny JSON-RPC helper used across the tech.saac contract tests."""
    payload: dict = {"jsonrpc": "2.0", "method": method, "id": 1}
    if params is not None:
        payload["params"] = params
    headers = {
        "Authorization": f"ApiKey {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    with httpx.Client(timeout=timeout) as http:
        resp = http.post(url, json=payload, headers=headers)
    resp.raise_for_status()
    return resp.json()
