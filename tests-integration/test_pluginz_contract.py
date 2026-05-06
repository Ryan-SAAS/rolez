"""Live contract tests against pluginz.startanaicompany.com.

Mirrors the skillz/agentz contracts. Pluginz is a sister registry — once
deployed at pluginz.startanaicompany.com it should expose the same shape
rolez already consumes for skillz/agentz.

If pluginz isn't deployed yet OR PLUGINZ_TOKEN isn't set, every test
here SKIPs cleanly (no failures), so this file is safe to run pre-launch.
Once pluginz is live the tests start exercising the real API.
"""
from __future__ import annotations

import os

import httpx
import pytest

from app.clients.pluginz import PluginzClient, PluginzNotFound
from conftest import run

pytestmark = pytest.mark.integration

PLUGINZ_URL_DEFAULT = "https://pluginz.startanaicompany.com"


@pytest.fixture
def pluginz_token() -> str:
    val = os.environ.get("PLUGINZ_TOKEN")
    if not val:
        pytest.skip("PLUGINZ_TOKEN not set — skip live pluginz contract")
    return val


@pytest.fixture
def pluginz_url() -> str:
    return os.environ.get("PLUGINZ_API_URL", PLUGINZ_URL_DEFAULT)


def _service_reachable(url: str, timeout: float) -> bool:
    """Pluginz isn't deployed yet — skip the whole file if the host is dead."""
    try:
        with httpx.Client(timeout=timeout) as http:
            r = http.get(f"{url}/")
            return r.status_code < 500
    except httpx.HTTPError:
        return False


def _first_plugin_name(pluginz_url: str, pluginz_token: str, timeout: float) -> str:
    headers = {"Authorization": f"Bearer {pluginz_token}", "Accept": "application/json"}
    with httpx.Client(timeout=timeout) as http:
        resp = http.get(f"{pluginz_url}/api/v1/plugins?limit=1", headers=headers)
    if resp.status_code == 401:
        pytest.skip("pluginz rejected PLUGINZ_TOKEN — skip rather than fail")
    resp.raise_for_status()
    items = resp.json().get("items") or []
    if not items:
        pytest.skip("pluginz registry is empty — nothing to probe")
    return items[0]["name"]


def test_pluginz_root_responds(pluginz_url, http_timeout):
    if not _service_reachable(pluginz_url, http_timeout):
        pytest.skip(f"pluginz not reachable at {pluginz_url} — skip until deployed")
    with httpx.Client(timeout=http_timeout) as http:
        resp = http.get(f"{pluginz_url}/")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("name") == "pluginz"
    endpoints = body.get("endpoints", {})
    agent_path = endpoints.get("agent") or endpoints.get("public")
    assert agent_path == "/api/v1"


def test_pluginz_get_plugin_response_shape(pluginz_url, pluginz_token, http_timeout):
    if not _service_reachable(pluginz_url, http_timeout):
        pytest.skip(f"pluginz not reachable at {pluginz_url} — skip until deployed")
    name = _first_plugin_name(pluginz_url, pluginz_token, http_timeout)

    client = PluginzClient(base_url=pluginz_url, token=pluginz_token, timeout=http_timeout)
    data = run(client.get_plugin(name))

    # The fields rolez's resolver depends on. If pluginz renames any of these,
    # this test fires before rolez's resolver silently breaks.
    assert isinstance(data.get("name"), str)
    assert data["name"] == name
    assert "latest_version" in data, (
        "plugin response missing `latest_version` — rolez resolver will break"
    )
    assert data["latest_version"] is None or isinstance(data["latest_version"], str)
    assert isinstance(data.get("versions", []), list)


def test_pluginz_404_for_unknown_plugin(pluginz_url, pluginz_token, http_timeout):
    if not _service_reachable(pluginz_url, http_timeout):
        pytest.skip(f"pluginz not reachable at {pluginz_url} — skip until deployed")
    client = PluginzClient(base_url=pluginz_url, token=pluginz_token, timeout=http_timeout)
    with pytest.raises(PluginzNotFound):
        run(client.get_plugin("__rolez_integration_test_definitely_missing__"))


def test_pluginz_401_without_token(pluginz_url, http_timeout):
    if not _service_reachable(pluginz_url, http_timeout):
        pytest.skip(f"pluginz not reachable at {pluginz_url} — skip until deployed")
    with httpx.Client(timeout=http_timeout) as http:
        resp = http.get(f"{pluginz_url}/api/v1/plugins?limit=1")
    assert resp.status_code == 401, (
        f"pluginz returned {resp.status_code} without a token — auth requirement may have changed"
    )
