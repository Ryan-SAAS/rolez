"""Resolver coverage for the pluginz path.

Mirrors the existing skill/subagent resolver tests in test_resolver.py +
test_coverage_gaps.py — same shape, different upstream client. Pluginz
isn't deployed yet, but its `GET /api/v1/plugins/{name}` shape is
committed in the pluginz repo and matches skillz/agentz, so we can mock
it confidently.
"""
from __future__ import annotations

import httpx
import pytest
import respx

from app.clients.pluginz import (
    PluginzClient,
    PluginzError,
    PluginzNotFound,
    PluginzUnreachable,
)
from app.resolver import ResolverError, resolve_draft
from app.validation import RoleManifestDraft


def _draft(plugins: list[dict] | None = None) -> RoleManifestDraft:
    body: dict = {
        "image": {"ref": "saac/x", "version": "1.0.0"},
        "skills": [],
        "subagents": [],
        "context": "",
    }
    if plugins is not None:
        body["plugins"] = plugins
    return RoleManifestDraft(**body)


# ---- client-level ------------------------------------------------------


@respx.mock
async def test_pluginz_get_plugin_returns_latest():
    respx.get("https://pluginz.example/api/v1/plugins/code-helpers").mock(
        return_value=httpx.Response(200, json={"name": "code-helpers", "latest_version": "1.4.0", "versions": []})
    )
    c = PluginzClient(base_url="https://pluginz.example", token="t")
    out = await c.get_plugin("code-helpers")
    assert out["latest_version"] == "1.4.0"


@respx.mock
async def test_pluginz_404_raises_not_found():
    respx.get("https://pluginz.example/api/v1/plugins/nope").mock(
        return_value=httpx.Response(404, json={"detail": "not found"})
    )
    c = PluginzClient(base_url="https://pluginz.example", token="t")
    with pytest.raises(PluginzNotFound):
        await c.get_plugin("nope")


@respx.mock
async def test_pluginz_5xx_raises_unreachable():
    respx.get("https://pluginz.example/api/v1/plugins/x").mock(
        return_value=httpx.Response(503)
    )
    c = PluginzClient(base_url="https://pluginz.example", token="t")
    with pytest.raises(PluginzUnreachable) as ei:
        await c.get_plugin("x")
    assert ei.value.status_code == 503


@respx.mock
async def test_pluginz_4xx_raises_pluginz_error():
    respx.get("https://pluginz.example/api/v1/plugins/x").mock(
        return_value=httpx.Response(400)
    )
    c = PluginzClient(base_url="https://pluginz.example", token="t")
    with pytest.raises(PluginzError) as ei:
        await c.get_plugin("x")
    assert ei.value.status_code == 400


@respx.mock
async def test_pluginz_network_error_raises_unreachable():
    respx.get("https://pluginz.example/api/v1/plugins/x").mock(side_effect=httpx.ConnectError("boom"))
    c = PluginzClient(base_url="https://pluginz.example", token="t")
    with pytest.raises(PluginzUnreachable):
        await c.get_plugin("x")


# ---- resolver-level ----------------------------------------------------


@respx.mock
async def test_resolver_pins_plugin_latest():
    respx.get("https://pluginz.example/api/v1/plugins/code-helpers").mock(
        return_value=httpx.Response(200, json={"latest_version": "1.4.0"})
    )
    resolved = await resolve_draft(_draft(plugins=[{"name": "code-helpers", "version": "latest"}]))
    assert resolved.plugins[0].version == "1.4.0"


@respx.mock
async def test_resolver_passes_pinned_plugin_through():
    # Already-pinned plugins must NOT trigger an upstream call.
    resolved = await resolve_draft(_draft(plugins=[{"name": "code-helpers", "version": "1.2.3"}]))
    assert resolved.plugins[0].version == "1.2.3"


@respx.mock
async def test_resolver_unknown_plugin_error_mapped():
    respx.get("https://pluginz.example/api/v1/plugins/missing").mock(
        return_value=httpx.Response(404, json={"detail": "not found"})
    )
    with pytest.raises(ResolverError):
        await resolve_draft(_draft(plugins=[{"name": "missing", "version": "latest"}]))


@respx.mock
async def test_resolver_pluginz_outage_marked_as_upstream():
    respx.get("https://pluginz.example/api/v1/plugins/x").mock(
        return_value=httpx.Response(503)
    )
    with pytest.raises(ResolverError) as ei:
        await resolve_draft(_draft(plugins=[{"name": "x", "version": "latest"}]))
    assert ei.value.is_upstream_outage is True


@respx.mock
async def test_resolver_plugin_missing_latest_version_field_errors():
    respx.get("https://pluginz.example/api/v1/plugins/x").mock(
        return_value=httpx.Response(200, json={"name": "x"})  # no latest_version
    )
    with pytest.raises(ResolverError, match="no published versions"):
        await resolve_draft(_draft(plugins=[{"name": "x", "version": "latest"}]))


# ---- end-to-end through admin POST -------------------------------------


@respx.mock
async def test_admin_post_resolves_plugin_latest_to_pinned(client, admin_headers):
    respx.get("https://pluginz.example/api/v1/plugins/code-helpers").mock(
        return_value=httpx.Response(200, json={"latest_version": "1.4.0"})
    )
    body = {
        "slug": "with-plugin",
        "tags": [],
        "manifest": {
            "image": {"ref": "saac/x", "version": "1.0.0"},
            "skills": [],
            "subagents": [],
            "plugins": [{"name": "code-helpers", "version": "latest"}],
            "context": "",
        },
    }
    resp = await client.post("/api/admin/roles", headers=admin_headers, json=body)
    assert resp.status_code == 201, resp.text
    out = resp.json()
    assert out["manifest"]["plugins"][0]["version"] == "1.4.0"
