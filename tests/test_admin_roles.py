from __future__ import annotations

import httpx
import respx


def _draft_body(**overrides) -> dict:
    body = {
        "slug": "support-agent",
        "display_name": "Support Lead",
        "description": "Handles customer support",
        "kind": "agent",
        "tags": ["support"],
        "manifest": {
            "image": {"ref": "saac/support-agent", "version": "1.0.0"},
            "identity": {"name": "Support Lead"},
            "skills": [{"name": "pdf-generator", "version": "latest"}],
            "subagents": [{"name": "code-reviewer", "version": "latest"}],
            "tools": {"allow": ["Read"], "disallow": []},
            "mcp_servers": [],
            "prompts": [],
            "inputs": [],
            "outputs": [],
            "consumed_integrations": [],
            "required_variables": [{"name": "SUPPORT_CHANNEL", "description": "..."}],
            "communication_rules": {
                "can_dm": [], "receives_dm": [], "listens_to": [], "posts_to": [],
            },
            "context_files": [{"path": "CLAUDE.md", "content": "# support\n"}],
        },
    }
    body.update(overrides)
    return body


def _mock_upstreams(skill_version: str = "1.2.3", subagent_version: str = "0.5.0") -> None:
    respx.get("https://skillz.example/api/v1/skills/pdf-generator").mock(
        return_value=httpx.Response(200, json={"latest_version": skill_version})
    )
    respx.get("https://agentz.example/api/v1/agents/code-reviewer").mock(
        return_value=httpx.Response(200, json={"latest_version": subagent_version})
    )


@respx.mock
async def test_create_role_resolves_latest_and_returns_pinned(client, admin_headers):
    _mock_upstreams("1.2.3", "0.5.0")
    resp = await client.post("/api/admin/roles", headers=admin_headers, json=_draft_body())
    assert resp.status_code == 201, resp.text
    out = resp.json()
    assert out["slug"] == "support-agent"
    assert out["version"] == "0.1.0"
    assert out["manifest_sha256"]
    manifest = out["manifest"]
    assert manifest["skills"][0]["version"] == "1.2.3"
    assert manifest["subagents"][0]["version"] == "0.5.0"


@respx.mock
async def test_create_role_auto_bumps_version_on_change(client, admin_headers):
    _mock_upstreams("1.2.3", "0.5.0")
    r1 = await client.post("/api/admin/roles", headers=admin_headers, json=_draft_body())
    assert r1.status_code == 201
    assert r1.json()["version"] == "0.1.0"

    # Bump skill latest, omit `version` in body → should auto-bump to 0.1.1.
    _mock_upstreams("1.2.4", "0.5.0")
    r2 = await client.post("/api/admin/roles", headers=admin_headers, json=_draft_body())
    assert r2.status_code == 201, r2.text
    assert r2.json()["version"] == "0.1.1"


@respx.mock
async def test_create_role_idempotent_under_same_version_and_content(client, admin_headers):
    _mock_upstreams("1.2.3", "0.5.0")
    body = _draft_body(version="0.2.0")
    r1 = await client.post("/api/admin/roles", headers=admin_headers, json=body)
    assert r1.status_code == 201
    r2 = await client.post("/api/admin/roles", headers=admin_headers, json=body)
    assert r2.status_code in (200, 201)  # idempotent — same sha
    assert r2.json()["version"] == "0.2.0"
    assert r2.json()["manifest_sha256"] == r1.json()["manifest_sha256"]


@respx.mock
async def test_create_role_409_when_explicit_version_collides_with_different_content(
    client, admin_headers
):
    _mock_upstreams("1.2.3", "0.5.0")
    body = _draft_body(version="0.3.0")
    r1 = await client.post("/api/admin/roles", headers=admin_headers, json=body)
    assert r1.status_code == 201

    _mock_upstreams("9.9.9", "0.5.0")
    r2 = await client.post("/api/admin/roles", headers=admin_headers, json=body)
    assert r2.status_code == 409


async def test_create_role_requires_admin_apikey(client):
    resp = await client.post("/api/admin/roles", json=_draft_body())
    assert resp.status_code == 401


@respx.mock
async def test_list_roles_returns_created(client, admin_headers):
    _mock_upstreams()
    await client.post("/api/admin/roles", headers=admin_headers, json=_draft_body())
    resp = await client.get("/api/admin/roles", headers=admin_headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any(i["slug"] == "support-agent" for i in items)


@respx.mock
async def test_delete_role_soft_deletes(client, admin_headers):
    _mock_upstreams()
    await client.post("/api/admin/roles", headers=admin_headers, json=_draft_body())
    resp = await client.delete("/api/admin/roles/support-agent", headers=admin_headers)
    assert resp.status_code == 204

    listed = await client.get("/api/admin/roles", headers=admin_headers)
    assert all(i["slug"] != "support-agent" for i in listed.json()["items"])

    listed_with_deleted = await client.get(
        "/api/admin/roles?include_deleted=true", headers=admin_headers
    )
    assert any(i["slug"] == "support-agent" for i in listed_with_deleted.json()["items"])


@respx.mock
async def test_delete_specific_version(client, admin_headers):
    _mock_upstreams()
    await client.post("/api/admin/roles", headers=admin_headers, json=_draft_body(version="0.1.0"))
    await client.post("/api/admin/roles", headers=admin_headers, json=_draft_body(version="0.1.1"))
    resp = await client.delete(
        "/api/admin/roles/support-agent/versions/0.1.0", headers=admin_headers
    )
    assert resp.status_code == 204
    show = await client.get("/api/admin/roles/support-agent", headers=admin_headers)
    versions = [v["version"] for v in show.json()["versions"]]
    assert "0.1.0" not in versions
    assert "0.1.1" in versions
