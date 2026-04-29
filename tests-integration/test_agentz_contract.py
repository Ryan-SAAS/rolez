"""Live contract tests against agentz.startanaicompany.com."""
from __future__ import annotations

import httpx
import pytest

from app.clients.agentz import AgentzClient, AgentzNotFound
from conftest import run

pytestmark = pytest.mark.integration


def _first_agent_name(agentz_url: str, agentz_token: str, timeout: float) -> str:
    headers = {"Authorization": f"Bearer {agentz_token}", "Accept": "application/json"}
    with httpx.Client(timeout=timeout) as http:
        resp = http.get(f"{agentz_url}/api/v1/agents?limit=1", headers=headers)
    if resp.status_code == 401:
        pytest.skip("agentz rejected AGENTZ_TOKEN — skip rather than fail (token may be wrong env)")
    resp.raise_for_status()
    items = resp.json().get("items") or []
    if not items:
        pytest.skip("agentz registry is empty — nothing to probe")
    return items[0]["name"]


def test_agentz_root_responds(agentz_url, http_timeout):
    with httpx.Client(timeout=http_timeout) as http:
        resp = http.get(f"{agentz_url}/")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("name") == "agentz"
    endpoints = body.get("endpoints", {})
    agent_path = endpoints.get("agent") or endpoints.get("public")
    assert agent_path == "/api/v1"


def test_agentz_get_agent_response_shape(agentz_url, agentz_token, http_timeout):
    name = _first_agent_name(agentz_url, agentz_token, http_timeout)

    client = AgentzClient(base_url=agentz_url, token=agentz_token, timeout=http_timeout)
    data = run(client.get_agent(name))

    assert isinstance(data.get("name"), str)
    assert data["name"] == name
    assert "latest_version" in data, (
        "agentz response missing `latest_version` — rolez resolver will break"
    )
    assert data["latest_version"] is None or isinstance(data["latest_version"], str)
    assert isinstance(data.get("versions", []), list)


def test_agentz_404_for_unknown_agent(agentz_url, agentz_token, http_timeout):
    client = AgentzClient(base_url=agentz_url, token=agentz_token, timeout=http_timeout)
    with pytest.raises(AgentzNotFound):
        run(client.get_agent("__rolez_integration_test_definitely_missing__"))


def test_agentz_401_without_token(agentz_url, http_timeout):
    with httpx.Client(timeout=http_timeout) as http:
        resp = http.get(f"{agentz_url}/api/v1/agents?limit=1")
    assert resp.status_code == 401
