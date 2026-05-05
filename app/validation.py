from __future__ import annotations

import hashlib
import json
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
# OCI-style image reference: registry/path/name with optional ":tag".
# Permits the slash-separated namespacing tech.saac uses (saac/support-agent).
# Allows a-z 0-9 . _ - / and an optional :tag suffix. No spaces, no control
# characters, no backslashes.
IMAGE_REF_RE = re.compile(r"^[a-z0-9][a-z0-9._\-/]{0,253}(?::[A-Za-z0-9._\-]{1,128})?$")


def validate_slug(slug: str) -> None:
    if not isinstance(slug, str) or not NAME_RE.match(slug):
        raise ValueError(f"invalid slug {slug!r}: must match {NAME_RE.pattern}")


def validate_version(version: str) -> None:
    if not isinstance(version, str) or not SEMVER_RE.match(version):
        raise ValueError(f"invalid semver version {version!r}")


def validate_image_ref(ref: str) -> None:
    if not isinstance(ref, str) or not IMAGE_REF_RE.match(ref):
        raise ValueError(
            f"invalid image ref {ref!r}: must match {IMAGE_REF_RE.pattern}"
        )


def _validate_name_field(v: str) -> str:
    validate_slug(v)
    return v


def _validate_pinned_version_field(v: str) -> str:
    validate_version(v)
    return v


def _validate_resolvable_version_field(v: str) -> str:
    """Drafts allow `latest`; resolved manifests do not."""
    if v == "latest":
        return v
    validate_version(v)
    return v


# ---- Pinned-version refs (used in stored manifests) ---------------------


class SkillRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    version: str

    @field_validator("name")
    @classmethod
    def _vname(cls, v: str) -> str:
        return _validate_name_field(v)

    @field_validator("version")
    @classmethod
    def _vver(cls, v: str) -> str:
        return _validate_pinned_version_field(v)


class SubagentRef(SkillRef):
    pass


class ImageRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ref: str
    version: str

    @field_validator("ref")
    @classmethod
    def _vref(cls, v: str) -> str:
        validate_image_ref(v)
        return v

    @field_validator("version")
    @classmethod
    def _vver(cls, v: str) -> str:
        return _validate_pinned_version_field(v)


# ---- Draft refs (allow "latest") ---------------------------------------


class SkillRefDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    version: str = "latest"

    @field_validator("name")
    @classmethod
    def _vname(cls, v: str) -> str:
        return _validate_name_field(v)

    @field_validator("version")
    @classmethod
    def _vver(cls, v: str) -> str:
        return _validate_resolvable_version_field(v)


class SubagentRefDraft(SkillRefDraft):
    pass


class ImageRefDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ref: str
    version: str = "latest"

    @field_validator("ref")
    @classmethod
    def _vref(cls, v: str) -> str:
        validate_image_ref(v)
        return v

    @field_validator("version")
    @classmethod
    def _vver(cls, v: str) -> str:
        return _validate_resolvable_version_field(v)


# ---- Sub-blocks ---------------------------------------------------------


class Identity(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    icon: str | None = None
    tone: str | None = None
    description: str | None = None


class ContextFile(BaseModel):
    """A single context file the role contributes. Mapped at provision time
    to tech.saac's update_agent_context shape:
      - name == "CLAUDE.md"        → claude_md.content
      - name == "HIVE-RULES.md"    → hive_rules_md.content
      - everything else            → custom_files[]
    """

    model_config = ConfigDict(extra="forbid")
    name: str
    content: str

    @field_validator("name")
    @classmethod
    def _safe_name(cls, v: str) -> str:
        if not v:
            raise ValueError("context_files[].name must be non-empty")
        if v.startswith("/"):
            raise ValueError("context_files[].name must be relative")
        if "\\" in v:
            raise ValueError("context_files[].name must not contain backslashes")
        if "\x00" in v:
            raise ValueError("context_files[].name must not contain NUL")
        if len(v) >= 2 and v[1] == ":":
            raise ValueError("context_files[].name must be relative (no drive letter)")
        parts = v.split("/")
        if any(p == ".." for p in parts):
            raise ValueError("context_files[].name must not contain '..' segments")
        return v


# ---- Top-level manifests -----------------------------------------------


class _RoleManifestBase(BaseModel):
    """Rolez owns the recruiting brief: image, identity, skills, subagents,
    and the role-specific context that gets appended to tech.saac's default.
    Everything else (tools, prompts, inputs/outputs, integrations,
    variables, communication rules) is tech.saac's concern, controlled via
    its admin UI — not part of the role manifest."""

    model_config = ConfigDict(extra="ignore")
    identity: Identity
    context_files: list[ContextFile] = Field(default_factory=list)


class RoleManifest(_RoleManifestBase):
    """A resolved role manifest — all skill/subagent/image refs are pinned."""
    image: ImageRef
    skills: list[SkillRef] = Field(default_factory=list)
    subagents: list[SubagentRef] = Field(default_factory=list)


class RoleManifestDraft(_RoleManifestBase):
    """A draft submitted to /api/admin/roles — refs may be `latest`."""
    image: ImageRefDraft
    skills: list[SkillRefDraft] = Field(default_factory=list)
    subagents: list[SubagentRefDraft] = Field(default_factory=list)


# ---- Determinism helpers -----------------------------------------------


def canonical_json(value) -> str:
    """Stable JSON serialization for byte-deterministic hashing."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_of_manifest(manifest: dict) -> str:
    return hashlib.sha256(canonical_json(manifest).encode("utf-8")).hexdigest()
