"""Smoke probe against a deployed rolez instance.

Optional — gated on ``ROLEZ_INTEGRATION_URL`` (e.g.
``https://rolez.startanaicompany.com``). Useful as a post-deploy
healthcheck and as an early-warning if our own service drifts from
the contract its CLI assumes.
"""
from __future__ import annotations

import os

import httpx
import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def rolez_url() -> str:
    url = os.environ.get("ROLEZ_INTEGRATION_URL")
    if not url:
        pytest.skip("ROLEZ_INTEGRATION_URL not set — skip live rolez smoke")
    return url.rstrip("/")


def test_rolez_health(rolez_url, http_timeout):
    with httpx.Client(timeout=http_timeout) as http:
        resp = http.get(f"{rolez_url}/health")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body == {"status": "ok", "db": "ok"}


def test_rolez_root_advertises_endpoints(rolez_url, http_timeout):
    with httpx.Client(timeout=http_timeout) as http:
        resp = http.get(f"{rolez_url}/")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("name") == "rolez"
    endpoints = body.get("endpoints") or {}
    assert endpoints.get("public") == "/api/v1"
    assert endpoints.get("admin") == "/api/admin"
    assert endpoints.get("cli") == "/cli/rolez"
    # /metrics is intentionally NOT advertised (no metrics router yet).
    assert "metrics" not in endpoints


def test_rolez_cli_bootstrap_endpoint(rolez_url, http_timeout):
    with httpx.Client(timeout=http_timeout) as http:
        resp = http.get(f"{rolez_url}/cli/rolez")
    assert resp.status_code == 200
    body = resp.text
    assert body.startswith("#!/usr/bin/env python3"), "CLI bootstrap is not a python script"
    assert "argparse" in body, "CLI seems too small to be the real script"


def test_rolez_v1_requires_auth(rolez_url, http_timeout):
    with httpx.Client(timeout=http_timeout) as http:
        resp = http.get(f"{rolez_url}/api/v1/roles")
    assert resp.status_code == 401, "rolez /api/v1 must require auth"
    body = resp.json()
    assert "missing api key" in (body.get("detail") or "").lower()


def test_rolez_admin_requires_auth(rolez_url, http_timeout):
    with httpx.Client(timeout=http_timeout) as http:
        resp = http.get(f"{rolez_url}/api/admin/roles")
    assert resp.status_code == 401
