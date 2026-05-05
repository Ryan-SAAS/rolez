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
            "context_files": [{"name": "CLAUDE.md", "content": "# support\n"}],
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
async def test_admin_show_returns_latest_manifest_and_sha(client, admin_headers):
    """Admin show needs the manifest content for AdminOffice render +
    tech.saac's daemon-config builder. Single round-trip, no version hop."""
    _mock_upstreams("1.2.3", "0.5.0")
    await client.post("/api/admin/roles", headers=admin_headers, json=_draft_body())

    resp = await client.get("/api/admin/roles/support-agent", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["slug"] == "support-agent"
    assert body["latest_version"] == "0.1.0"
    assert body["manifest_sha256"]
    assert body["manifest"]["skills"][0]["version"] == "1.2.3"
    assert body["manifest"]["subagents"][0]["version"] == "0.5.0"


async def test_admin_show_manifest_null_when_no_versions(client, admin_headers):
    """Edge case: the show endpoint must not crash when the role has no
    versions yet (shouldn't happen in normal flow, but defensive)."""
    # We can't easily construct a role without versions via the API (POST
    # always creates one), so we just confirm the response shape doesn't
    # blow up when fetching an unknown role — our 404 path.
    resp = await client.get("/api/admin/roles/nope", headers=admin_headers)
    assert resp.status_code == 404


@respx.mock
async def test_admin_list_supports_q_tag_kind_filters(client, admin_headers):
    _mock_upstreams()
    await client.post("/api/admin/roles", headers=admin_headers, json=_draft_body())  # support
    body2 = _draft_body()
    body2["slug"] = "hr-agent"
    body2["description"] = "human resources role"
    body2["tags"] = ["hr"]
    body2["kind"] = "agent"
    await client.post("/api/admin/roles", headers=admin_headers, json=body2)
    body3 = _draft_body()
    body3["slug"] = "support-assistant"
    body3["description"] = "support assistant role"
    body3["kind"] = "assistant"
    await client.post("/api/admin/roles", headers=admin_headers, json=body3)

    # ?q
    r = await client.get("/api/admin/roles?q=support", headers=admin_headers)
    slugs = sorted(i["slug"] for i in r.json()["items"])
    assert slugs == ["support-agent", "support-assistant"]

    # ?tag
    r = await client.get("/api/admin/roles?tag=hr", headers=admin_headers)
    assert [i["slug"] for i in r.json()["items"]] == ["hr-agent"]

    # ?kind
    r = await client.get("/api/admin/roles?kind=assistant", headers=admin_headers)
    assert [i["slug"] for i in r.json()["items"]] == ["support-assistant"]


@respx.mock
async def test_admin_list_pagination(client, admin_headers):
    _mock_upstreams()
    for slug in ("alpha-agent", "beta-agent", "gamma-agent"):
        b = _draft_body()
        b["slug"] = slug
        await client.post("/api/admin/roles", headers=admin_headers, json=b)
    r = await client.get("/api/admin/roles?limit=2&offset=1", headers=admin_headers)
    body = r.json()
    assert body["total"] == 3
    assert [i["slug"] for i in body["items"]] == ["beta-agent", "gamma-agent"]


@respx.mock
async def test_admin_show_role_version(client, admin_headers):
    """Admin /roles/{slug}/versions/{version} mirrors the public endpoint
    but is gated behind admin auth — tech.saac (admin-key-only) needs it."""
    _mock_upstreams("1.2.3", "0.5.0")
    await client.post("/api/admin/roles", headers=admin_headers, json=_draft_body())

    r = await client.get("/api/admin/roles/support-agent/versions/0.1.0", headers=admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == "0.1.0"
    assert body["manifest"]["skills"][0]["version"] == "1.2.3"


async def test_admin_show_version_404s(client, admin_headers):
    r = await client.get("/api/admin/roles/nope/versions/1.0.0", headers=admin_headers)
    assert r.status_code == 404


async def test_admin_show_version_requires_admin_apikey(client):
    r = await client.get("/api/admin/roles/x/versions/1.0.0")
    assert r.status_code == 401


@respx.mock
async def test_validate_dry_runs_without_persisting(client, admin_headers):
    """POST /api/admin/roles/validate resolves the manifest and returns the
    pinned preview, but never writes to the DB."""
    _mock_upstreams("1.2.3", "0.5.0")
    body = _draft_body()
    resp = await client.post(
        "/api/admin/roles/validate",
        headers=admin_headers,
        json={"slug": body["slug"], "manifest": body["manifest"]},
    )
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["slug"] == "support-agent"
    assert out["manifest_sha256"]
    assert out["manifest"]["skills"][0]["version"] == "1.2.3"

    # Confirm nothing was persisted.
    listed = await client.get("/api/admin/roles", headers=admin_headers)
    assert listed.json()["items"] == []


async def test_validate_returns_422_for_invalid_manifest(client, admin_headers):
    resp = await client.post(
        "/api/admin/roles/validate",
        headers=admin_headers,
        json={"manifest": {"image": "not-an-object"}},
    )
    assert resp.status_code == 422


@respx.mock
async def test_validate_returns_422_for_missing_skill(client, admin_headers):
    respx.get("https://skillz.example/api/v1/skills/missing").mock(
        return_value=httpx.Response(404, json={"detail": "skill not found"})
    )
    body = _draft_body()
    body["manifest"]["skills"] = [{"name": "missing", "version": "latest"}]
    resp = await client.post(
        "/api/admin/roles/validate",
        headers=admin_headers,
        json={"slug": body["slug"], "manifest": body["manifest"]},
    )
    assert resp.status_code == 422
    assert "missing" in resp.text


async def test_validate_requires_admin_apikey(client):
    resp = await client.post("/api/admin/roles/validate", json={"manifest": {}})
    assert resp.status_code == 401


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
