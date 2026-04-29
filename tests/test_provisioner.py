from __future__ import annotations

import json

import httpx
import pytest
import respx
from sqlalchemy import select


def _draft_body(slug: str = "support-agent", **overrides) -> dict:
    body = {
        "slug": slug,
        "display_name": slug,
        "description": f"role {slug}",
        "kind": "agent",
        "tags": [],
        "manifest": {
            "image": {"ref": f"saac/{slug}", "version": "1.0.0"},
            "identity": {"name": slug},
            "skills": [{"name": "pdf-generator", "version": "1.2.3"}],
            "subagents": [{"name": "code-reviewer", "version": "0.5.0"}],
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
            "context_files": [],
        },
    }
    body.update(overrides)
    return body


@pytest.fixture(autouse=True)
def _clear_upstream_cache():
    from app.upstream_auth import _CACHE
    _CACHE.clear()
    yield
    _CACHE.clear()


def _mock_techsaac_valid():
    """Single MCP route that handles BOTH the upstream-auth probe (tools/list)
    and the create_agent call. We dispatch based on the JSON-RPC method.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        method = body.get("method")
        if method == "tools/list":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": {"tools": []}})
        if method == "tools/call":
            tool = body["params"]["name"]
            args = body["params"]["arguments"]
            return httpx.Response(200, json={
                "jsonrpc": "2.0", "id": body["id"],
                "result": {"agent_id": "agent-uuid", "status": "starting", "tool": tool, "echo": args},
            })
        return httpx.Response(400, json={"error": "unknown method"})

    respx.post("https://techsaac.example/api/mcp").mock(side_effect=handler)


@respx.mock
async def test_provision_creates_agent_and_records_event(client, admin_headers, agent_headers):
    _mock_techsaac_valid()
    await client.post("/api/admin/roles", headers=admin_headers, json=_draft_body())

    resp = await client.post(
        "/api/v1/roles/support-agent/provision",
        headers=agent_headers,
        json={
            "organization_id": "org-uuid",
            "product_id": "prod-uuid",
            "name": "support-eu",
            "variables": {"SUPPORT_CHANNEL": "#eu-support"},
        },
    )
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["agent_id"] == "agent-uuid"
    assert out["role_slug"] == "support-agent"
    assert out["role_version"] == "0.1.0"
    assert out["status"] == 200

    # ProvisionEvent recorded
    from app.db import get_session_factory
    from app.models import ProvisionEvent
    factory = get_session_factory()
    async with factory() as s:
        rows = (await s.execute(select(ProvisionEvent))).scalars().all()
        assert len(rows) == 1
        assert rows[0].agent_id_returned == "agent-uuid"
        assert rows[0].agent_name == "support-eu"
        assert rows[0].status == 200


@respx.mock
async def test_provision_missing_required_variable_fails(client, admin_headers, agent_headers):
    _mock_techsaac_valid()
    await client.post("/api/admin/roles", headers=admin_headers, json=_draft_body())

    resp = await client.post(
        "/api/v1/roles/support-agent/provision",
        headers=agent_headers,
        json={"organization_id": "org-uuid", "product_id": "p", "name": "support-eu"},
    )
    assert resp.status_code == 422
    assert "SUPPORT_CHANNEL" in resp.text


@respx.mock
async def test_provision_forwards_bindings_as_refs_no_secrets(client, admin_headers, agent_headers):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["method"] == "tools/list":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": {"tools": []}})
        # tools/call create_agent
        captured["args"] = body["params"]["arguments"]
        return httpx.Response(200, json={
            "jsonrpc": "2.0", "id": body["id"],
            "result": {"agent_id": "agent-uuid", "status": "starting"},
        })

    respx.post("https://techsaac.example/api/mcp").mock(side_effect=handler)

    await client.post("/api/admin/roles", headers=admin_headers, json=_draft_body())
    resp = await client.post(
        "/api/v1/roles/support-agent/provision",
        headers=agent_headers,
        json={
            "organization_id": "org-uuid",
            "product_id": "p",
            "name": "support-eu",
            "variables": {"SUPPORT_CHANNEL": "#eu"},
            "integration_bindings": [{"catalog_slug": "zendesk", "connection_id": "conn-uuid"}],
        },
    )
    assert resp.status_code == 200, resp.text

    args = captured["args"]
    # Bindings forwarded as refs:
    assert args["integration_bindings"] == [{"catalog_slug": "zendesk", "connection_id": "conn-uuid"}]
    # No secret-shaped keys leaked into env (we only ship variables + bindings):
    raw = json.dumps(args)
    assert "ZENDESK_API_KEY" not in raw  # rolez never resolves the secret value


@respx.mock
async def test_provision_merges_extras_later_wins(client, admin_headers, agent_headers):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["method"] == "tools/list":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": {"tools": []}})
        captured["args"] = body["params"]["arguments"]
        return httpx.Response(200, json={
            "jsonrpc": "2.0", "id": body["id"],
            "result": {"agent_id": "agent-uuid"},
        })

    respx.post("https://techsaac.example/api/mcp").mock(side_effect=handler)
    await client.post("/api/admin/roles", headers=admin_headers, json=_draft_body())

    resp = await client.post(
        "/api/v1/roles/support-agent/provision",
        headers=agent_headers,
        json={
            "organization_id": "org-uuid",
            "product_id": "p",
            "name": "support-eu",
            "variables": {"SUPPORT_CHANNEL": "#eu"},
            "extra_skills": [
                {"name": "pdf-generator", "version": "9.9.9"},  # overrides base 1.2.3
                {"name": "csv-tools", "version": "0.4.1"},
            ],
            "extra_subagents": [{"name": "log-grepper", "version": "0.1.0"}],
        },
    )
    assert resp.status_code == 200, resp.text

    skills = {s["name"]: s["version"] for s in captured["args"]["manifest"]["skills"]}
    assert skills["pdf-generator"] == "9.9.9"  # later wins
    assert skills["csv-tools"] == "0.4.1"
    sub = {s["name"]: s["version"] for s in captured["args"]["manifest"]["subagents"]}
    assert sub["code-reviewer"] == "0.5.0"
    assert sub["log-grepper"] == "0.1.0"


@respx.mock
async def test_provision_relays_techsaac_error(client, admin_headers, agent_headers):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["method"] == "tools/list":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": {"tools": []}})
        return httpx.Response(403, json={"error": "FORBIDDEN", "message": "no permission"})

    respx.post("https://techsaac.example/api/mcp").mock(side_effect=handler)
    await client.post("/api/admin/roles", headers=admin_headers, json=_draft_body())

    resp = await client.post(
        "/api/v1/roles/support-agent/provision",
        headers=agent_headers,
        json={
            "organization_id": "org-uuid",
            "product_id": "p",
            "name": "support-eu",
            "variables": {"SUPPORT_CHANNEL": "#eu"},
        },
    )
    # Relay tech.saac's status verbatim.
    assert resp.status_code == 403, resp.text

    from app.db import get_session_factory
    from app.models import ProvisionEvent
    factory = get_session_factory()
    async with factory() as s:
        row = (await s.execute(select(ProvisionEvent))).scalar_one()
        assert row.status == 403
        assert row.agent_id_returned is None
        assert row.error is not None


@respx.mock
async def test_provision_404_when_role_unknown(client, agent_headers):
    respx.post("https://techsaac.example/api/mcp").mock(
        return_value=httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {"tools": []}})
    )
    resp = await client.post(
        "/api/v1/roles/unknown/provision",
        headers=agent_headers,
        json={"organization_id": "o", "product_id": "p", "name": "n", "variables": {}},
    )
    assert resp.status_code == 404


@respx.mock
async def test_provision_502_when_techsaac_returns_no_agent_id(client, admin_headers, agent_headers):
    """If tech.saac responds 200 but neither {agent_id} nor {agent: {id}} is
    present, treat as protocol drift — record + 502, don't pretend it succeeded."""
    def handler(request):
        body = json.loads(request.content)
        if body["method"] == "tools/list":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": {"tools": []}})
        return httpx.Response(200, json={
            "jsonrpc": "2.0", "id": body["id"],
            "result": {"status": "starting", "queue_position": 1},  # NO agent_id
        })

    respx.post("https://techsaac.example/api/mcp").mock(side_effect=handler)
    await client.post("/api/admin/roles", headers=admin_headers, json=_draft_body())

    resp = await client.post(
        "/api/v1/roles/support-agent/provision",
        headers=agent_headers,
        json={
            "organization_id": "o", "product_id": "p", "name": "support-eu",
            "variables": {"SUPPORT_CHANNEL": "#x"},
        },
    )
    assert resp.status_code == 502, resp.text

    from app.db import get_session_factory
    from app.models import ProvisionEvent
    factory = get_session_factory()
    async with factory() as s:
        row = (await s.execute(select(ProvisionEvent))).scalar_one()
        assert row.status == 502
        assert row.agent_id_returned is None
        assert row.error and "agent id" in row.error.lower()


@respx.mock
async def test_provision_503_when_techsaac_unreachable(client, admin_headers, agent_headers):
    """A valid token in the cache + an unreachable upstream → 503 with a
    provision_event recorded so the audit log captures the outage."""
    # First, prime the upstream-auth cache with a valid token result so the
    # request gets past the auth check.
    from app.upstream_auth import _CACHE, _CacheEntry, _key
    import time as _time
    _CACHE[_key("test-assistant-mcp-token")] = _CacheEntry(
        valid=True, expires_at=_time.monotonic() + 60
    )

    # Make the create_agent call itself unreachable.
    respx.post("https://techsaac.example/api/mcp").mock(side_effect=httpx.ConnectError("boom"))

    await client.post("/api/admin/roles", headers=admin_headers, json=_draft_body())
    resp = await client.post(
        "/api/v1/roles/support-agent/provision",
        headers=agent_headers,
        json={
            "organization_id": "o", "product_id": "p", "name": "support-eu",
            "variables": {"SUPPORT_CHANNEL": "#x"},
        },
    )
    assert resp.status_code == 503

    from app.db import get_session_factory
    from app.models import ProvisionEvent
    factory = get_session_factory()
    async with factory() as s:
        row = (await s.execute(select(ProvisionEvent))).scalar_one()
        assert row.status == 503


@respx.mock
async def test_provision_502_when_techsaac_returns_jsonrpc_error(client, admin_headers, agent_headers):
    """JSON-RPC error in a 200 response → 502 (we can't trust upstream's intent)."""
    def handler(request):
        body = json.loads(request.content)
        if body["method"] == "tools/list":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": {}})
        return httpx.Response(200, json={
            "jsonrpc": "2.0", "id": body["id"],
            "error": {"code": -32603, "message": "internal tool error"},
        })

    respx.post("https://techsaac.example/api/mcp").mock(side_effect=handler)
    await client.post("/api/admin/roles", headers=admin_headers, json=_draft_body())

    resp = await client.post(
        "/api/v1/roles/support-agent/provision",
        headers=agent_headers,
        json={
            "organization_id": "o", "product_id": "p", "name": "support-eu",
            "variables": {"SUPPORT_CHANNEL": "#x"},
        },
    )
    assert resp.status_code == 502


@respx.mock
async def test_provision_404_when_only_version_was_deleted(client, admin_headers, agent_headers):
    """Create a role, delete its only version, then attempt to provision.
    Should 404 and NOT write a provision_event (resolution failed before
    any tech.saac call)."""
    respx.post("https://techsaac.example/api/mcp").mock(
        return_value=httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {"tools": []}})
    )
    await client.post("/api/admin/roles", headers=admin_headers, json=_draft_body())
    await client.delete("/api/admin/roles/support-agent/versions/0.1.0", headers=admin_headers)

    resp = await client.post(
        "/api/v1/roles/support-agent/provision",
        headers=agent_headers,
        json={
            "organization_id": "o", "product_id": "p", "name": "support-eu",
            "variables": {"SUPPORT_CHANNEL": "#x"},
        },
    )
    assert resp.status_code == 404

    from app.db import get_session_factory
    from app.models import ProvisionEvent
    factory = get_session_factory()
    async with factory() as s:
        rows = (await s.execute(select(ProvisionEvent))).scalars().all()
        assert rows == []
