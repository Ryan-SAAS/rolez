from __future__ import annotations

import httpx
import pytest
import respx


def _draft_body(slug: str = "support-agent", **overrides) -> dict:
    body = {
        "slug": slug,
        "display_name": slug,
        "description": f"role {slug}",
        "kind": "agent",
        "tags": ["support"],
        "manifest": {
            "image": {"ref": f"saac/{slug}", "version": "1.0.0"},
            "identity": {"name": slug},
            "skills": [{"name": "pdf-generator", "version": "1.2.3"}],
            "subagents": [{"name": "code-reviewer", "version": "0.5.0"}],
            "context_files": [],
        },
    }
    body.update(overrides)
    return body


def _mock_techsaac_valid():
    respx.post("https://techsaac.example/api/mcp").mock(
        return_value=httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {"tools": []}})
    )


def _mock_techsaac_invalid():
    respx.post("https://techsaac.example/api/mcp").mock(
        return_value=httpx.Response(401, json={"error": "UNAUTHORIZED"})
    )


@pytest.fixture(autouse=True)
def _clear_upstream_cache():
    from app.upstream_auth import _CACHE
    _CACHE.clear()
    yield
    _CACHE.clear()


@respx.mock
async def test_public_list_requires_valid_caller_token(client, admin_headers, agent_headers):
    _mock_techsaac_valid()
    await client.post("/api/admin/roles", headers=admin_headers, json=_draft_body())

    resp = await client.get("/api/v1/roles", headers=agent_headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any(i["slug"] == "support-agent" for i in items)


@respx.mock
async def test_public_list_401_when_token_invalid_upstream(client, agent_headers):
    _mock_techsaac_invalid()
    resp = await client.get("/api/v1/roles", headers=agent_headers)
    assert resp.status_code == 401


@respx.mock
async def test_public_list_401_when_no_header(client):
    _mock_techsaac_valid()
    resp = await client.get("/api/v1/roles")
    assert resp.status_code == 401


@respx.mock
async def test_public_show_returns_pinned_manifest(client, admin_headers, agent_headers):
    _mock_techsaac_valid()
    await client.post("/api/admin/roles", headers=admin_headers, json=_draft_body())

    resp = await client.get("/api/v1/roles/support-agent", headers=agent_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["slug"] == "support-agent"
    assert body["latest_version"] == "0.1.0"
    assert body["manifest"]["skills"][0]["version"] == "1.2.3"
    assert body["manifest"]["subagents"][0]["version"] == "0.5.0"


@respx.mock
async def test_public_show_specific_version(client, admin_headers, agent_headers):
    _mock_techsaac_valid()
    await client.post("/api/admin/roles", headers=admin_headers, json=_draft_body(version="0.1.0"))
    await client.post("/api/admin/roles", headers=admin_headers, json=_draft_body(version="0.2.0"))

    resp = await client.get(
        "/api/v1/roles/support-agent/versions/0.1.0", headers=agent_headers
    )
    assert resp.status_code == 200
    assert resp.json()["version"] == "0.1.0"


@respx.mock
async def test_public_search_filters_by_query(client, admin_headers, agent_headers):
    _mock_techsaac_valid()
    await client.post("/api/admin/roles", headers=admin_headers, json=_draft_body("support-agent"))
    await client.post("/api/admin/roles", headers=admin_headers, json=_draft_body("hr-agent"))

    resp = await client.get("/api/v1/roles/search?q=support", headers=agent_headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert all("support" in i["slug"] or "support" in (i.get("description") or "") for i in items)
    assert any(i["slug"] == "support-agent" for i in items)


@respx.mock
async def test_public_show_404_for_unknown(client, agent_headers):
    _mock_techsaac_valid()
    resp = await client.get("/api/v1/roles/unknown", headers=agent_headers)
    assert resp.status_code == 404


@respx.mock
async def test_public_list_pagination_offset_and_limit(client, admin_headers, agent_headers):
    """Pagination on /api/v1/roles — total counts everything (post-filter),
    items[] is the requested page."""
    _mock_techsaac_valid()
    for slug in ("alpha-agent", "beta-agent", "gamma-agent"):
        await client.post("/api/admin/roles", headers=admin_headers, json=_draft_body(slug))

    resp = await client.get("/api/v1/roles?limit=2", headers=agent_headers)
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["items"][0]["slug"] == "alpha-agent"
    assert body["items"][1]["slug"] == "beta-agent"

    resp2 = await client.get("/api/v1/roles?limit=2&offset=2", headers=agent_headers)
    body2 = resp2.json()
    assert body2["total"] == 3
    assert len(body2["items"]) == 1
    assert body2["items"][0]["slug"] == "gamma-agent"


@respx.mock
async def test_public_list_rejects_oversized_limit(client, agent_headers):
    _mock_techsaac_valid()
    resp = await client.get("/api/v1/roles?limit=999", headers=agent_headers)
    assert resp.status_code == 422  # FastAPI Query(le=200) enforces


@respx.mock
async def test_public_list_excludes_soft_deleted(client, admin_headers, agent_headers):
    _mock_techsaac_valid()
    await client.post("/api/admin/roles", headers=admin_headers, json=_draft_body("dead-agent"))
    await client.delete("/api/admin/roles/dead-agent", headers=admin_headers)

    resp = await client.get("/api/v1/roles", headers=agent_headers)
    items = resp.json()["items"]
    assert all(i["slug"] != "dead-agent" for i in items)
