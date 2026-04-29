"""Tests for paths the main suite didn't exercise.

Each test here corresponds to a specific missing line surfaced by
`pytest --cov=app --cov-report=term-missing`. The intent is behaviour
coverage, not line-counting — every test asserts a real contract.
"""
from __future__ import annotations

import httpx
import pytest
import respx

from app.clients.agentz import AgentzClient, AgentzError
from app.clients.skillz import SkillzClient, SkillzError
from app.clients.techsaac import TechsaacClient, TechsaacError
from app.config import Settings
from app.resolver import ResolverError, resolve_draft
from app.validation import RoleManifestDraft


@pytest.fixture(autouse=True)
def _clear_upstream_cache():
    from app.upstream_auth import _CACHE
    _CACHE.clear()
    yield
    _CACHE.clear()


# --- public router: 503 when tech.saac is unreachable -------------------

@respx.mock
async def test_public_list_503_when_techsaac_unreachable(client, agent_headers):
    respx.post("https://techsaac.example/api/mcp").mock(side_effect=httpx.ConnectError("boom"))
    resp = await client.get("/api/v1/roles", headers=agent_headers)
    assert resp.status_code == 503
    assert "upstream auth unavailable" in resp.text.lower()


# --- public router: show_role_version 404s ------------------------------

@respx.mock
async def test_public_show_version_404_when_role_unknown(client, agent_headers):
    respx.post("https://techsaac.example/api/mcp").mock(
        return_value=httpx.Response(200, json={"result": {}})
    )
    resp = await client.get("/api/v1/roles/nope/versions/0.1.0", headers=agent_headers)
    assert resp.status_code == 404


@respx.mock
async def test_public_show_version_404_when_version_unknown(client, admin_headers, agent_headers):
    respx.post("https://techsaac.example/api/mcp").mock(
        return_value=httpx.Response(200, json={"result": {}})
    )
    body = _admin_seed_body("seed-agent")
    await client.post("/api/admin/roles", headers=admin_headers, json=body)

    resp = await client.get(
        "/api/v1/roles/seed-agent/versions/9.9.9", headers=agent_headers
    )
    assert resp.status_code == 404


# --- admin router: 422 paths --------------------------------------------

async def test_admin_create_invalid_manifest_422(client, admin_headers):
    bad = {
        "slug": "broken",
        "kind": "agent",
        "tags": [],
        "manifest": {"image": "not-an-object"},  # schema violation
    }
    resp = await client.post("/api/admin/roles", headers=admin_headers, json=bad)
    assert resp.status_code == 422
    assert "invalid manifest" in resp.text.lower() or "image" in resp.text.lower()


@respx.mock
async def test_admin_create_resolver_error_422(client, admin_headers):
    """If skillz says the referenced skill doesn't exist, admin POST → 422."""
    respx.get("https://skillz.example/api/v1/skills/missing-skill").mock(
        return_value=httpx.Response(404, json={"detail": "skill not found"})
    )
    body = _admin_seed_body("broken-agent")
    body["manifest"]["skills"] = [{"name": "missing-skill", "version": "latest"}]
    resp = await client.post("/api/admin/roles", headers=admin_headers, json=body)
    assert resp.status_code == 422
    assert "missing-skill" in resp.text


# --- admin router: delete-version 404 paths -----------------------------

async def test_admin_delete_role_404_when_unknown(client, admin_headers):
    resp = await client.delete("/api/admin/roles/never-existed", headers=admin_headers)
    assert resp.status_code == 404


async def test_admin_delete_version_404_when_role_unknown(client, admin_headers):
    resp = await client.delete(
        "/api/admin/roles/never-existed/versions/0.1.0", headers=admin_headers
    )
    assert resp.status_code == 404


@respx.mock
async def test_admin_delete_version_404_when_version_unknown(client, admin_headers):
    body = _admin_seed_body("ok-agent")
    await client.post("/api/admin/roles", headers=admin_headers, json=body)
    resp = await client.delete(
        "/api/admin/roles/ok-agent/versions/9.9.9", headers=admin_headers
    )
    assert resp.status_code == 404


@respx.mock
async def test_admin_show_404_when_unknown(client, admin_headers):
    resp = await client.get("/api/admin/roles/nope", headers=admin_headers)
    assert resp.status_code == 404


# --- provisioner: explicit version not found ----------------------------

@respx.mock
async def test_provision_404_when_version_unknown(client, admin_headers, agent_headers):
    respx.post("https://techsaac.example/api/mcp").mock(
        return_value=httpx.Response(200, json={"result": {}})
    )
    await client.post("/api/admin/roles", headers=admin_headers, json=_admin_seed_body())
    resp = await client.post(
        "/api/v1/roles/support-agent/provision",
        headers=agent_headers,
        json={
            "organization_id": "o", "product_id": "p", "name": "n",
            "variables": {"SUPPORT_CHANNEL": "#x"},
            "version": "9.9.9",
        },
    )
    assert resp.status_code == 404


# --- resolver: error mapping --------------------------------------------

@respx.mock
async def test_resolver_unknown_skill_error_mapped():
    respx.get("https://skillz.example/api/v1/skills/missing").mock(
        return_value=httpx.Response(404, json={"detail": "not found"})
    )
    draft = RoleManifestDraft(
        image={"ref": "saac/x", "version": "1.0.0"},
        identity={"name": "x"},
        skills=[{"name": "missing", "version": "latest"}],
        subagents=[],
        context_files=[],
    )
    with pytest.raises(ResolverError):
        await resolve_draft(draft)


@respx.mock
async def test_resolver_skillz_5xx_error_mapped():
    respx.get("https://skillz.example/api/v1/skills/x").mock(
        return_value=httpx.Response(503)
    )
    draft = RoleManifestDraft(
        image={"ref": "saac/x", "version": "1.0.0"},
        identity={"name": "x"},
        skills=[{"name": "x", "version": "latest"}],
        subagents=[],
        context_files=[],
    )
    with pytest.raises(ResolverError):
        await resolve_draft(draft)


@respx.mock
async def test_resolver_missing_latest_version_field_errors():
    respx.get("https://skillz.example/api/v1/skills/x").mock(
        return_value=httpx.Response(200, json={"name": "x"})  # no latest_version
    )
    draft = RoleManifestDraft(
        image={"ref": "saac/x", "version": "1.0.0"},
        identity={"name": "x"},
        skills=[{"name": "x", "version": "latest"}],
        subagents=[],
        context_files=[],
    )
    with pytest.raises(ResolverError, match="no published versions"):
        await resolve_draft(draft)


@respx.mock
async def test_resolver_agentz_error_mapped():
    respx.get("https://agentz.example/api/v1/agents/missing").mock(
        return_value=httpx.Response(503)
    )
    draft = RoleManifestDraft(
        image={"ref": "saac/x", "version": "1.0.0"},
        identity={"name": "x"},
        skills=[],
        subagents=[{"name": "missing", "version": "latest"}],
        context_files=[],
    )
    with pytest.raises(ResolverError):
        await resolve_draft(draft)


@respx.mock
async def test_resolver_agentz_missing_latest_version_field_errors():
    respx.get("https://agentz.example/api/v1/agents/y").mock(
        return_value=httpx.Response(200, json={"name": "y"})
    )
    draft = RoleManifestDraft(
        image={"ref": "saac/x", "version": "1.0.0"},
        identity={"name": "x"},
        skills=[],
        subagents=[{"name": "y", "version": "latest"}],
        context_files=[],
    )
    with pytest.raises(ResolverError, match="no published versions"):
        await resolve_draft(draft)


# --- client error mapping ----------------------------------------------

@respx.mock
async def test_skillz_5xx_raises_generic_error():
    respx.get("https://skillz.example/api/v1/skills/x").mock(
        return_value=httpx.Response(503, json={"error": "boom"})
    )
    c = SkillzClient(base_url="https://skillz.example", token="t")
    with pytest.raises(SkillzError):
        await c.get_skill("x")


@respx.mock
async def test_agentz_5xx_raises_generic_error():
    respx.get("https://agentz.example/api/v1/agents/x").mock(
        return_value=httpx.Response(503)
    )
    c = AgentzClient(base_url="https://agentz.example", token="t")
    with pytest.raises(AgentzError):
        await c.get_agent("x")


@respx.mock
async def test_techsaac_network_error_unreachable():
    respx.post("https://techsaac.example/api/mcp").mock(
        side_effect=httpx.ConnectError("boom")
    )
    c = TechsaacClient(base_url="https://techsaac.example/api/mcp")
    with pytest.raises(TechsaacError, match="unreachable"):
        await c.call_tool("x", {}, caller_token="t")


@respx.mock
async def test_techsaac_non_json_body_raises():
    respx.post("https://techsaac.example/api/mcp").mock(
        return_value=httpx.Response(200, text="not json", headers={"content-type": "text/plain"})
    )
    c = TechsaacClient(base_url="https://techsaac.example/api/mcp")
    with pytest.raises(TechsaacError, match="non-JSON"):
        await c.call_tool("x", {}, caller_token="t")


@respx.mock
async def test_techsaac_safe_body_falls_back_to_text_when_not_json():
    respx.post("https://techsaac.example/api/mcp").mock(
        return_value=httpx.Response(401, text="plain text body")
    )
    c = TechsaacClient(base_url="https://techsaac.example/api/mcp")
    with pytest.raises(TechsaacError) as ei:
        await c.call_tool("x", {}, caller_token="t")
    # _safe_body should have read the text body without throwing
    assert ei.value.body == "plain text body" or "plain text body" in str(ei.value.body)


# --- config: postgresql:// rewriting -----------------------------------

def test_config_rewrites_postgresql_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/db")
    s = Settings()
    assert s.database_url.startswith("postgresql+asyncpg://")


def test_config_rewrites_postgres_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@h:5432/db")
    s = Settings()
    assert s.database_url.startswith("postgresql+asyncpg://")


def test_config_csv_origins(monkeypatch):
    monkeypatch.setenv("ADMIN_ALLOWED_ORIGINS", "https://a.com, https://b.com")
    s = Settings()
    assert s.admin_allowed_origins == ["https://a.com", "https://b.com"]


# --- auth: extract_apikey edge cases ------------------------------------

def test_extract_apikey_rejects_other_schemes():
    from app.auth import extract_apikey
    assert extract_apikey("Basic dXNlcjpwYXNz") is None


def test_extract_apikey_returns_none_for_apikey_with_empty_token():
    from app.auth import extract_apikey
    # "ApiKey " with empty token should be treated as missing
    assert extract_apikey("ApiKey ") is None


# --- main: CLI not packaged ---------------------------------------------

async def test_cli_endpoint_returns_500_when_file_missing(client, monkeypatch):
    from app import main as main_module
    from pathlib import Path
    monkeypatch.setattr(main_module, "CLI_PATH", Path("/nonexistent/rolez"))
    resp = await client.get("/cli/rolez")
    assert resp.status_code == 500
    assert "not packaged" in resp.text.lower()


# --- helpers ------------------------------------------------------------

def _admin_seed_body(slug: str = "support-agent") -> dict:
    return {
        "slug": slug,
        "display_name": slug,
        "description": f"role {slug}",
        "kind": "agent",
        "tags": [],
        "manifest": {
            "image": {"ref": f"saac/{slug}", "version": "1.0.0"},
            "identity": {"name": slug},
            "skills": [],
            "subagents": [],
            "tools": {"allow": [], "disallow": []},
            "mcp_servers": [],
            "prompts": [],
            "inputs": [],
            "outputs": [],
            "consumed_integrations": [],
            "required_variables": [{"name": "SUPPORT_CHANNEL", "description": "..."}],
            "communication_rules": {
                "can_dm": [], "receives_dm": [], "listens_to": [], "posts_to": [],
            },
            "context_files": [],
        },
    }
