from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.validation import validate_slug, validate_version


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


class RoleValidateIn(BaseModel):
    """Dry-run validation request — same shape as RoleCreateIn but the
    server returns the resolved manifest preview without persisting."""

    model_config = ConfigDict(extra="forbid")

    slug: str | None = None
    manifest: dict[str, Any]

    @field_validator("slug")
    @classmethod
    def _vslug(cls, v: str | None) -> str | None:
        if v is None:
            return v
        validate_slug(v)
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
    # `manifest` / `manifest_sha256` are populated from the latest version row
    # so admin consumers (tech.saac AdminOffice + daemon-config builder) can
    # render the full role definition in one round-trip — no need to fetch
    # /versions/{v} after the show.
    manifest: dict[str, Any] | None = None
    manifest_sha256: str | None = None
    versions: list[RoleVersionOut] = Field(default_factory=list)


class RoleCreatedOut(BaseModel):
    slug: str
    version: str
    manifest_sha256: str
    manifest: dict[str, Any]
    created_at: datetime


class RoleValidatedOut(BaseModel):
    """Dry-run validation response — same fields as RoleCreatedOut except
    no created_at (nothing was persisted)."""

    slug: str | None = None
    manifest_sha256: str
    manifest: dict[str, Any]


class HealthOut(BaseModel):
    status: str
    db: str
