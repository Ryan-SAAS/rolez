"""Live contract tests against skillz.startanaicompany.com.

Pin the response shape rolez relies on. Uses the same ``SkillzClient``
rolez itself uses (driven via ``run(...)`` in a fresh loop), so a
contract change that breaks production also breaks the test.
"""
from __future__ import annotations

import httpx
import pytest

from app.clients.skillz import SkillzClient, SkillzNotFound
from conftest import run

pytestmark = pytest.mark.integration


def _first_skill_name(skillz_url: str, skillz_token: str, timeout: float) -> str:
    """Pull the first skill in the registry — whatever it happens to be."""
    headers = {"Authorization": f"Bearer {skillz_token}", "Accept": "application/json"}
    with httpx.Client(timeout=timeout) as http:
        resp = http.get(f"{skillz_url}/api/v1/skills?limit=1", headers=headers)
    resp.raise_for_status()
    items = resp.json().get("items") or []
    if not items:
        pytest.skip("skillz registry is empty — nothing to probe")
    return items[0]["name"]


def test_skillz_root_responds(skillz_url, http_timeout):
    """Sanity: the service is up and advertises the expected version envelope."""
    with httpx.Client(timeout=http_timeout) as http:
        resp = http.get(f"{skillz_url}/")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("name") == "skillz"
    endpoints = body.get("endpoints", {})
    agent_path = endpoints.get("agent") or endpoints.get("public")
    assert agent_path == "/api/v1", (
        f"skillz advertises {agent_path!r} for the agent API; rolez assumes /api/v1"
    )


def test_skillz_get_skill_response_shape(skillz_url, skillz_token, http_timeout):
    """The fields rolez's resolver depends on must remain present and typed
    correctly. If skillz renames `latest_version`, this test fails first."""
    name = _first_skill_name(skillz_url, skillz_token, http_timeout)

    client = SkillzClient(base_url=skillz_url, token=skillz_token, timeout=http_timeout)
    data = run(client.get_skill(name))

    assert isinstance(data.get("name"), str), "skill.name must be a string"
    assert data["name"] == name
    assert "latest_version" in data, (
        "skill response missing `latest_version` — rolez resolver will break"
    )
    assert data["latest_version"] is None or isinstance(data["latest_version"], str)
    assert isinstance(data.get("versions", []), list)


def test_skillz_404_for_unknown_skill(skillz_url, skillz_token, http_timeout):
    """Rolez maps 404 → ResolverError(not_found) → admin 422. If skillz
    starts returning 200 with an error envelope instead, that mapping breaks."""
    client = SkillzClient(base_url=skillz_url, token=skillz_token, timeout=http_timeout)
    with pytest.raises(SkillzNotFound):
        run(client.get_skill("__rolez_integration_test_definitely_missing__"))


def test_skillz_401_without_token(skillz_url, http_timeout):
    """Confirm skillz still requires the bearer token — if it ever goes
    public, rolez's auth handling on this path becomes dead code."""
    with httpx.Client(timeout=http_timeout) as http:
        resp = http.get(f"{skillz_url}/api/v1/skills?limit=1")
    assert resp.status_code == 401, (
        f"skillz returned {resp.status_code} without a token — auth requirement may have changed"
    )
