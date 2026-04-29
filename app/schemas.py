from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.validation import (
    SkillRefDraft,
    SubagentRefDraft,
    validate_slug,
    validate_version,
)


class IntegrationBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    catalog_slug: str
    connection_id: str


class RoleCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str
    display_name: str | None = None
    description: str | None = None
    kind: Literal["agent", "assistant"] | None = None
    tags: list[str] = Field(default_factory=list)
    manifest: dict[str, Any]
    version: str | None = Field(
        default=None,
        description="If omitted, the server bumps the latest patch version.",
    )

    @field_validator("slug")
    @classmethod
    def _vslug(cls, v: str) -> str:
        validate_slug(v)
        return v

    @field_validator("version")
    @classmethod
    def _vver(cls, v: str | None) -> str | None:
        if v is None:
            return v
        validate_version(v)
        return v


class RoleVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    version: str
    manifest_sha256: str
    created_at: datetime


class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    slug: str
    display_name: str | None = None
    description: str | None = None
    kind: str
    tags: list[str] = Field(default_factory=list)
    latest_version: str | None = None
    versions_count: int = 0
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class RoleListOut(BaseModel):
    total: int
    items: list[RoleOut]


class RoleDetailOut(RoleOut):
    versions: list[RoleVersionOut] = Field(default_factory=list)


class RoleCreatedOut(BaseModel):
    slug: str
    version: str
    manifest_sha256: str
    manifest: dict[str, Any]
    created_at: datetime


class ProvisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization_id: str
    product_id: str | None = None
    name: str
    variables: dict[str, str] = Field(default_factory=dict)
    integration_bindings: list[IntegrationBinding] = Field(default_factory=list)
    extra_skills: list[SkillRefDraft] = Field(default_factory=list)
    extra_subagents: list[SubagentRefDraft] = Field(default_factory=list)
    version: str = "latest"

    @field_validator("name")
    @classmethod
    def _vname(cls, v: str) -> str:
        validate_slug(v)
        return v

    @field_validator("version")
    @classmethod
    def _vver(cls, v: str) -> str:
        if v == "latest":
            return v
        validate_version(v)
        return v


class ProvisionOut(BaseModel):
    agent_id: str | None = None
    role_slug: str
    role_version: str
    status: int
    tech_saac_response: Any = None
    error: str | None = None


class ProvisionEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ts: datetime
    role_slug: str
    role_version: str
    organization_id: str | None = None
    product_id: str | None = None
    agent_name: str | None = None
    agent_id_returned: str | None = None
    status: int
    error: str | None = None


class HealthOut(BaseModel):
    status: str
    db: str
