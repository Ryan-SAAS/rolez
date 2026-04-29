from __future__ import annotations

import httpx
import pytest
import respx

from app.resolver import ResolverError, resolve_draft
from app.validation import RoleManifestDraft


def _draft(**overrides) -> RoleManifestDraft:
    """Default body keeps everything pinned so individual tests set `latest`
    only where they care to exercise resolution. Avoids accidental upstream
    calls in tests that aren't testing the relevant resolver path."""
    body = {
        "image": {"ref": "saac/support-agent", "version": "1.0.0"},
        "identity": {"name": "Support Lead"},
        "skills": [],
        "subagents": [],
        "tools": {"allow": [], "disallow": []},
        "mcp_servers": [],
        "prompts": [],
        "inputs": [],
        "outputs": [],
        "consumed_integrations": [],
        "required_variables": [],
        "communication_rules": {"can_dm": [], "receives_dm": [], "listens_to": [], "posts_to": []},
        "context_files": [],
    }
    body.update(overrides)
    return RoleManifestDraft(**body)


@respx.mock
async def test_resolves_skill_and_subagent_latest_to_pinned():
    respx.get("https://skillz.example/api/v1/skills/pdf-generator").mock(
        return_value=httpx.Response(200, json={"name": "pdf-generator", "latest_version": "1.2.3", "versions": []})
    )
    respx.get("https://agentz.example/api/v1/agents/code-reviewer").mock(
        return_value=httpx.Response(200, json={"name": "code-reviewer", "latest_version": "0.5.0", "versions": []})
    )
    resolved = await resolve_draft(
        _draft(
            skills=[{"name": "pdf-generator", "version": "latest"}],
            subagents=[{"name": "code-reviewer", "version": "latest"}],
        )
    )
    assert resolved.skills[0].version == "1.2.3"
    assert resolved.subagents[0].version == "0.5.0"


@respx.mock
async def test_resolved_pinned_versions_are_passed_through_unchanged():
    respx.get("https://skillz.example/api/v1/skills/pdf-generator").mock(
        return_value=httpx.Response(200, json={"name": "pdf-generator", "latest_version": "9.9.9", "versions": []})
    )
    draft = _draft(skills=[{"name": "pdf-generator", "version": "1.2.3"}])  # already pinned
    resolved = await resolve_draft(draft)
    assert resolved.skills[0].version == "1.2.3"


@respx.mock
async def test_unknown_skill_raises_resolver_error():
    respx.get("https://skillz.example/api/v1/skills/missing").mock(
        return_value=httpx.Response(404, json={"detail": "skill not found"})
    )
    with pytest.raises(ResolverError):
        await resolve_draft(_draft(skills=[{"name": "missing", "version": "latest"}]))


@respx.mock
async def test_unknown_subagent_raises_resolver_error():
    respx.get("https://agentz.example/api/v1/agents/missing").mock(
        return_value=httpx.Response(404, json={"detail": "agent not found"})
    )
    with pytest.raises(ResolverError):
        await resolve_draft(_draft(subagents=[{"name": "missing", "version": "latest"}]))


@respx.mock
async def test_resolver_passes_image_latest_through_unchanged():
    # No tech.saac image-catalog tool yet — resolver leaves image.version as
    # "latest" and lets tech.saac pick at provision time. The plan accepts
    # this as the deferred-resolution path.
    resolved = await resolve_draft(
        _draft(image={"ref": "saac/support-agent", "version": "latest"})
    )
    assert resolved.image.ref == "saac/support-agent"
    assert resolved.image.version == "latest"
