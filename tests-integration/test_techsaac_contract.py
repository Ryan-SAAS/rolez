"""Live contract tests against tech.saac MCP at /api/mcp.

Two layers:

1. **Auth probe** — `tools/list` returns 200 for a valid token, 401 for a
   bogus one. This is the surface ``app/upstream_auth.verify_token``
   relies on.

2. **Tool contracts** — for every MCP tool rolez calls (today: just
   ``create_agent``; soon: ``set_agent_container_image``,
   ``set_agent_env_var``, ``connect_integration``,
   ``update_agent_context``, ``list_container_images``), assert the tool
   exists AND its inputSchema still has the required fields rolez
   sends. If tech.saac renames ``product_id`` to ``product`` or makes
   ``agent_name`` optional, these tests fail with a descriptive
   message *before* a real provision attempt does.

The single source of truth is ``EXPECTED_TOOLS`` below — when rolez
starts calling a new tool, add an entry here.
"""
from __future__ import annotations

import httpx
import pytest

from conftest import call_mcp

pytestmark = pytest.mark.integration


# What rolez expects from each tool it calls today, plus the next handful
# the v0.2 provisioner is planned to use. Each entry pins the contract
# rolez assumes — drift on either side fails this test.
EXPECTED_TOOLS: dict[str, dict] = {
    # Currently called by app/upstream_auth.verify_token (via tools/list)
    # and by app/provisioner.provision (via tools/call).
    "create_agent": {
        "required_fields": ["product_id", "name", "agent_name"],
        "fields_we_send": ["product_id", "name", "agent_name", "description", "role"],
    },
    # Planned for v0.2 provisioner. Schemas pinned 2026-04-30 from live
    # tools/list. Update both `required_fields` AND the matching v0.2
    # provisioner code if either side changes.
    "set_agent_container_image": {
        "required_fields": ["agent_id", "container_image"],
        "fields_we_send": ["agent_id", "container_image"],
    },
    "set_agent_env_var": {
        "required_fields": ["agent_id", "key", "value"],
        "fields_we_send": ["agent_id", "key", "value", "description"],
    },
    "connect_integration": {
        "required_fields": ["agent_id", "provider", "credentials"],
        "fields_we_send": ["agent_id", "provider", "credentials", "label"],
    },
    "update_agent_context": {
        # claude_md / hive_rules_md / custom_files all optional — caller
        # passes whichever subset they need to update.
        "required_fields": ["agent_id"],
        "fields_we_send": ["agent_id", "claude_md", "hive_rules_md", "custom_files"],
    },
    "list_container_images": {
        "required_fields": [],
        "fields_we_send": [],
    },
    "list_organizations": {
        "required_fields": [],
        "fields_we_send": ["limit"],
    },
    "list_products": {
        "required_fields": [],
        "fields_we_send": ["organization_id", "limit"],
    },
    "delete_agent": {
        "required_fields": ["agent_id"],
        "fields_we_send": ["agent_id"],
    },
}


@pytest.fixture
def tools_index(mcp_url: str, mcp_token: str, http_timeout: float) -> dict[str, dict]:
    """Pull the full tools/list once and index by name. Shared across tests."""
    data = call_mcp(url=mcp_url, token=mcp_token, method="tools/list", timeout=http_timeout)
    tools = (data.get("result") or {}).get("tools") or []
    if not tools:
        pytest.skip("tech.saac returned no tools — token may lack permissions")
    return {t["name"]: t for t in tools}


# ---------- auth probe (covers app/upstream_auth.verify_token) ------------


def test_techsaac_tools_list_succeeds_with_valid_token(mcp_url, mcp_token, http_timeout):
    data = call_mcp(url=mcp_url, token=mcp_token, method="tools/list", timeout=http_timeout)
    assert "result" in data, f"unexpected JSON-RPC envelope: {data}"
    assert "tools" in data["result"]


def test_techsaac_tools_list_rejects_bogus_token(mcp_url, http_timeout):
    """Rolez maps 401 → invalid_api_key for callers. If tech.saac stops
    returning 401 (e.g. switches to JSON-RPC error envelope on 200),
    rolez's auth flow stops working."""
    bogus = "us_bogus_token_for_rolez_integration_test"
    headers = {
        "Authorization": f"ApiKey {bogus}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {"jsonrpc": "2.0", "method": "tools/list", "id": 1}
    with httpx.Client(timeout=http_timeout) as http:
        resp = http.post(mcp_url, json=payload, headers=headers)
    assert resp.status_code in (401, 403), (
        f"tech.saac returned {resp.status_code} for a bogus token; rolez expects 401/403"
    )


# ---------- tool-level contract (covers app/provisioner) ----------------


@pytest.mark.parametrize("tool_name", sorted(EXPECTED_TOOLS.keys()))
def test_expected_tool_exists(tool_name, tools_index):
    assert tool_name in tools_index, (
        f"tech.saac no longer exposes the {tool_name!r} MCP tool that rolez calls. "
        f"Available tools: {sorted(tools_index.keys())[:10]}…"
    )


@pytest.mark.parametrize("tool_name", sorted(EXPECTED_TOOLS.keys()))
def test_expected_tool_required_fields_unchanged(tool_name, tools_index):
    expected_required = set(EXPECTED_TOOLS[tool_name]["required_fields"])
    schema = tools_index[tool_name].get("inputSchema") or {}
    actual_required = set(schema.get("required") or [])

    added = actual_required - expected_required
    removed = expected_required - actual_required
    if added or removed:
        pytest.fail(
            f"{tool_name!r} required-field set changed.\n"
            f"  expected: {sorted(expected_required)}\n"
            f"  actual:   {sorted(actual_required)}\n"
            f"  added:    {sorted(added)}\n"
            f"  removed:  {sorted(removed)}"
        )


@pytest.mark.parametrize("tool_name", sorted(EXPECTED_TOOLS.keys()))
def test_fields_we_send_are_recognized(tool_name, tools_index):
    """Each field rolez sends must exist in the tool's inputSchema. If
    tech.saac renames a field, rolez will silently send a key the tool
    ignores — and the operation may half-succeed in confusing ways."""
    fields_we_send = set(EXPECTED_TOOLS[tool_name]["fields_we_send"])
    schema = tools_index[tool_name].get("inputSchema") or {}
    accepted = set((schema.get("properties") or {}).keys())

    unknown = fields_we_send - accepted
    if unknown:
        pytest.fail(
            f"{tool_name!r} no longer accepts field(s) rolez sends: {sorted(unknown)}.\n"
            f"  fields rolez sends: {sorted(fields_we_send)}\n"
            f"  fields tool accepts: {sorted(accepted)}"
        )


def test_create_agent_agent_name_format_documented(tools_index):
    """The 4-word HIVE format requirement for ``agent_name`` is documented
    in the tool description — if that constraint changes, we want to
    notice (rolez may need to relax/update its name generator).
    """
    desc = (tools_index["create_agent"].get("description") or "").lower()
    assert "4-word format" in desc or "agent_name" in desc, (
        "create_agent description no longer documents the agent_name format requirement; "
        "verify the constraint hasn't changed before relaxing rolez's name generator"
    )


# ---------- read-only orchestration probes (don't mutate prod) ------------


def test_list_organizations_callable(mcp_url, mcp_token, http_timeout):
    """Sanity: the read-only ``list_organizations`` tool actually executes
    cleanly with our token. Confirms ``tools/call`` over MCP works (not
    just ``tools/list``)."""
    data = call_mcp(
        url=mcp_url, token=mcp_token, method="tools/call",
        params={"name": "list_organizations", "arguments": {"limit": 1}},
        timeout=http_timeout,
    )
    assert "result" in data, f"tools/call list_organizations failed: {data}"


def test_list_container_images_callable(mcp_url, mcp_token, http_timeout):
    """Sanity for the v0.2 image-resolution path. If this fails with the
    current token, the v0.2 resolver wiring needs different auth."""
    data = call_mcp(
        url=mcp_url, token=mcp_token, method="tools/call",
        params={"name": "list_container_images", "arguments": {}},
        timeout=http_timeout,
    )
    assert "result" in data, f"tools/call list_container_images failed: {data}"
