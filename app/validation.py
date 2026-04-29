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


def validate_slug(slug: str) -> None:
    if not isinstance(slug, str) or not NAME_RE.match(slug):
        raise ValueError(f"invalid slug {slug!r}: must match {NAME_RE.pattern}")


def validate_version(version: str) -> None:
    if not isinstance(version, str) or not SEMVER_RE.match(version):
        raise ValueError(f"invalid semver version {version!r}")


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


class Tools(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allow: list[str] = Field(default_factory=list)
    disallow: list[str] = Field(default_factory=list)


class Prompt(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    body: str
    trigger_source: str | None = None
    trigger_config: dict = Field(default_factory=dict)


class IOEdge(BaseModel):
    model_config = ConfigDict(extra="ignore")
    channel: str
    capability: str | None = None


class ConsumedIntegration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    catalog_slug: str
    env_needed: list[str] = Field(default_factory=list)


class RequiredVariable(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    description: str | None = None
    default: str | None = None


class CommunicationRules(BaseModel):
    model_config = ConfigDict(extra="forbid")
    can_dm: list[str] = Field(default_factory=list)
    receives_dm: list[str] = Field(default_factory=list)
    listens_to: list[str] = Field(default_factory=list)
    posts_to: list[str] = Field(default_factory=list)


class ContextFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    content: str

    @field_validator("path")
    @classmethod
    def _safe_path(cls, v: str) -> str:
        if not v:
            raise ValueError("context_files[].path must be non-empty")
        if v.startswith("/"):
            raise ValueError("context_files[].path must be relative")
        if ".." in v.split("/"):
            raise ValueError("context_files[].path must not contain '..' segments")
        return v


# ---- Top-level manifests -----------------------------------------------


class _RoleManifestBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    identity: Identity
    tools: Tools = Field(default_factory=Tools)
    mcp_servers: list[str] = Field(default_factory=list)
    prompts: list[Prompt] = Field(default_factory=list)
    inputs: list[IOEdge] = Field(default_factory=list)
    outputs: list[IOEdge] = Field(default_factory=list)
    consumed_integrations: list[ConsumedIntegration] = Field(default_factory=list)
    required_variables: list[RequiredVariable] = Field(default_factory=list)
    communication_rules: CommunicationRules = Field(default_factory=CommunicationRules)
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
