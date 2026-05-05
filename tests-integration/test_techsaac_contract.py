"""Live contract tests against tech.saac MCP at /api/mcp.

After the scope trim, rolez calls tech.saac for **one thing only**: validating
incoming caller tokens via ``tools/list`` (the cheapest possible probe).
Rolez no longer provisions agents — that's tech.saac's job via its own CLI
and ``create_agent`` MCP tool with the new ``rolez_slug`` argument.

So this contract is small:

1. **Auth probe** — ``tools/list`` returns 200 for a valid token, 401 for a
   bogus one. This is the surface ``app/upstream_auth.verify_token``
   relies on.

2. **Read-only tool sanity** — ``tools/call list_organizations`` round-trips
   cleanly, confirming JSON-RPC ``tools/call`` works (not just
   ``tools/list``). Not used by rolez itself, but if this fails the
   broader MCP transport is broken.

If the day comes that rolez again needs to call specific tools (e.g. an
admin proxy reads ``list_container_images``), add an ``EXPECTED_TOOLS``
dict here pinning their schemas. For now there's no such dict — every
shape concern is on the tech.saac side.
"""
from __future__ import annotations

import httpx
import pytest

from conftest import call_mcp

pytestmark = pytest.mark.integration


# ---------- auth probe (covers app/upstream_auth.verify_token) ------------


def test_techsaac_tools_list_succeeds_with_valid_token(mcp_url, mcp_token, http_timeout):
    data = call_mcp(url=mcp_url, token=mcp_token, method="tools/list", timeout=http_timeout)
    assert "result" in data, f"unexpected JSON-RPC envelope: {data}"
    assert "tools" in data["result"]


def test_techsaac_tools_list_rejects_bogus_token(mcp_url, http_timeout):
    """Rolez maps 401 → invalid_api_key for callers. If tech.saac stops
    returning 401 (e.g. switches to a JSON-RPC error envelope on 200),
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


# ---------- read-only tools/call sanity (transport check) -----------------


def test_techsaac_tools_call_round_trips(mcp_url, mcp_token, http_timeout):
    """Sanity: a read-only ``tools/call`` round-trips through MCP. Uses
    ``list_organizations`` because it's safe (no mutation, no required
    args). If this fails, the JSON-RPC transport is broken — every
    eventual rolez admin proxy call would fail too."""
    data = call_mcp(
        url=mcp_url, token=mcp_token, method="tools/call",
        params={"name": "list_organizations", "arguments": {"limit": 1}},
        timeout=http_timeout,
    )
    assert "result" in data, f"tools/call list_organizations failed: {data}"
