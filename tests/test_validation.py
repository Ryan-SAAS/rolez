from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.validation import (
    RoleManifest,
    RoleManifestDraft,
    SkillRef,
    SubagentRef,
    canonical_json,
    sha256_of_manifest,
    validate_slug,
    validate_version,
)


def test_validate_slug_accepts_lowercase():
    validate_slug("support-agent")
    validate_slug("a")
    validate_slug("a.b_c-1")


def test_validate_slug_rejects_invalid():
    with pytest.raises(ValueError):
        validate_slug("Support-Agent")  # uppercase
    with pytest.raises(ValueError):
        validate_slug("-leading")
    with pytest.raises(ValueError):
        validate_slug("")
    with pytest.raises(ValueError):
        validate_slug("with spaces")


def test_validate_version_accepts_semver():
    validate_version("0.1.0")
    validate_version("1.2.3-beta.1")
    validate_version("10.20.30")


def test_validate_version_rejects_non_semver():
    with pytest.raises(ValueError):
        validate_version("v1.2.3")
    with pytest.raises(ValueError):
        validate_version("1.2")
    with pytest.raises(ValueError):
        validate_version("latest")


def test_skillref_rejects_latest_in_resolved_manifest():
    """A *resolved* RoleManifest must never carry `latest` — only pinned semver."""
    with pytest.raises(ValidationError):
        SkillRef(name="pdf-generator", version="latest")


def test_skillref_rejects_invalid_name():
    with pytest.raises(ValidationError):
        SkillRef(name="Bad Name", version="1.0.0")


def test_subagentref_pinned_only():
    SubagentRef(name="code-reviewer", version="0.5.0")
    with pytest.raises(ValidationError):
        SubagentRef(name="code-reviewer", version="latest")


def _full_manifest() -> dict:
    return {
        "image": {"ref": "saac/support-agent", "version": "1.4.0"},
        "identity": {"name": "Support Lead", "icon": "🎧", "tone": "calm", "description": "..."},
        "skills": [{"name": "pdf-generator", "version": "1.2.3"}],
        "subagents": [{"name": "code-reviewer", "version": "0.5.0"}],
        "tools": {"allow": ["Read", "Edit"], "disallow": []},
        "mcp_servers": ["tech-saac"],
        "prompts": [],
        "inputs": [],
        "outputs": [],
        "consumed_integrations": [{"catalog_slug": "zendesk", "env_needed": ["ZENDESK_API_KEY"]}],
        "required_variables": [{"name": "SUPPORT_CHANNEL", "description": "...", "default": None}],
        "communication_rules": {
            "can_dm": ["product-owner"],
            "receives_dm": ["*"],
            "listens_to": ["#support"],
            "posts_to": ["#support"],
        },
        "context_files": [{"path": "CLAUDE.md", "content": "# Support role\n"}],
    }


def test_role_manifest_round_trips():
    m = RoleManifest(**_full_manifest())
    assert m.image.ref == "saac/support-agent"
    assert m.skills[0].name == "pdf-generator"
    assert m.context_files[0].path == "CLAUDE.md"


def test_context_files_reject_path_traversal():
    bad = _full_manifest()
    bad["context_files"] = [{"path": "../escape.md", "content": "x"}]
    with pytest.raises(ValidationError):
        RoleManifest(**bad)


def test_context_files_reject_absolute_paths():
    bad = _full_manifest()
    bad["context_files"] = [{"path": "/etc/passwd", "content": "x"}]
    with pytest.raises(ValidationError):
        RoleManifest(**bad)


def test_context_files_require_non_empty_path():
    bad = _full_manifest()
    bad["context_files"] = [{"path": "", "content": "x"}]
    with pytest.raises(ValidationError):
        RoleManifest(**bad)


def test_role_manifest_draft_allows_latest_for_skills():
    draft = RoleManifestDraft(
        **{
            **_full_manifest(),
            "skills": [{"name": "pdf-generator", "version": "latest"}],
            "subagents": [{"name": "code-reviewer", "version": "latest"}],
            "image": {"ref": "saac/support-agent", "version": "latest"},
        }
    )
    assert draft.skills[0].version == "latest"


def test_canonical_json_is_deterministic():
    a = {"b": 1, "a": [3, 2, 1], "c": {"y": 1, "x": 2}}
    b = {"a": [3, 2, 1], "c": {"x": 2, "y": 1}, "b": 1}
    assert canonical_json(a) == canonical_json(b)


def test_sha256_stable_across_key_orderings():
    a = _full_manifest()
    b = dict(reversed(list(a.items())))
    assert sha256_of_manifest(a) == sha256_of_manifest(b)
