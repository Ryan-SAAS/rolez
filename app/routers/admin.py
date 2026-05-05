from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from packaging.version import InvalidVersion, Version
from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import require_admin_apikey
from app.db import get_session
from app.models import RoleTemplate, RoleTemplateVersion
from app.resolver import ResolverError, resolve_draft
from app.schemas import (
    RoleCreatedOut,
    RoleCreateIn,
    RoleDetailOut,
    RoleListOut,
    RoleOut,
    RoleValidatedOut,
    RoleValidateIn,
    RoleVersionOut,
)
from app.validation import RoleManifestDraft, sha256_of_manifest

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _select_role_with_versions():
    """Reused query stem: a RoleTemplate with eagerly-loaded versions.
    Centralises the eager-load policy used by every read endpoint here and
    in public.py."""
    return select(RoleTemplate).options(selectinload(RoleTemplate.versions))


def _latest_row(versions: list[RoleTemplateVersion]) -> RoleTemplateVersion | None:
    if not versions:
        return None
    try:
        return max(versions, key=lambda v: Version(v.version))
    except InvalidVersion:
        return versions[0]


def _to_role_out(r: RoleTemplate) -> RoleOut:
    latest = _latest_row(list(r.versions))
    return RoleOut(
        slug=r.slug,
        display_name=r.display_name,
        description=r.description,
        kind=r.kind,
        tags=list(r.tags or []),
        latest_version=latest.version if latest else None,
        versions_count=len(r.versions),
        created_at=r.created_at,
        updated_at=r.updated_at,
        deleted_at=r.deleted_at,
    )


def _bump_patch(version: str) -> str:
    try:
        v = Version(version)
    except InvalidVersion:
        return "0.1.0"
    return f"{v.major}.{v.minor}.{v.micro + 1}"


@router.get("/roles", response_model=RoleListOut)
async def list_roles(
    _: Annotated[str, Depends(require_admin_apikey)],
    session: AsyncSession = Depends(get_session),
    include_deleted: bool = Query(default=False),
    tag: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> RoleListOut:
    """Mirrors the public list filters (q/tag/kind) so AdminOffice gets the
    same query surface here. include_deleted is admin-only — the public
    surface always hides soft-deleted rows."""
    stmt = _select_role_with_versions().order_by(RoleTemplate.slug)
    if not include_deleted:
        stmt = stmt.where(RoleTemplate.deleted_at.is_(None))
    if kind:
        stmt = stmt.where(RoleTemplate.kind == kind)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(RoleTemplate.slug.ilike(like), RoleTemplate.description.ilike(like)))
    rows = (await session.execute(stmt)).scalars().all()
    if tag:
        rows = [r for r in rows if tag in (r.tags or [])]
    total = len(rows)
    items = [_to_role_out(r) for r in rows[offset : offset + limit]]
    return RoleListOut(total=total, items=items)


@router.get("/roles/{slug}", response_model=RoleDetailOut)
async def show_role(
    slug: str,
    _: Annotated[str, Depends(require_admin_apikey)],
    session: AsyncSession = Depends(get_session),
) -> RoleDetailOut:
    """Returns the role's metadata + the **latest version's manifest** + sha256
    so the AdminOffice and tech.saac's daemon-config builder can render /
    consume the role in a single round-trip."""
    role = await session.scalar(
        _select_role_with_versions().where(RoleTemplate.slug == slug)
    )
    if role is None:
        raise HTTPException(status_code=404, detail="role not found")
    latest = _latest_row(list(role.versions))
    base = _to_role_out(role).model_dump()
    return RoleDetailOut(
        **base,
        manifest=latest.manifest if latest else None,
        manifest_sha256=latest.manifest_sha256 if latest else None,
        versions=[RoleVersionOut.model_validate(v) for v in role.versions],
    )


@router.get("/roles/{slug}/versions/{version}")
async def show_role_version(
    slug: str,
    version: str,
    _: Annotated[str, Depends(require_admin_apikey)],
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Mirror of the public /api/v1/.../versions/{v} endpoint, gated behind
    admin auth so tech.saac (which only has the admin key, not a us_* MCP
    token) can fetch a specific version's manifest."""
    role = await session.scalar(
        _select_role_with_versions().where(RoleTemplate.slug == slug)
    )
    if role is None:
        raise HTTPException(status_code=404, detail="role not found")
    rv = next((v for v in role.versions if v.version == version), None)
    if rv is None:
        raise HTTPException(status_code=404, detail="version not found")
    return {
        "slug": role.slug,
        "version": rv.version,
        "manifest_sha256": rv.manifest_sha256,
        "manifest": rv.manifest,
        "created_at": rv.created_at.isoformat() if rv.created_at else None,
    }


@router.post("/roles", response_model=RoleCreatedOut, status_code=201)
async def create_role(
    body: RoleCreateIn,
    _: Annotated[str, Depends(require_admin_apikey)],
    session: AsyncSession = Depends(get_session),
) -> RoleCreatedOut:
    try:
        draft = RoleManifestDraft(**body.manifest)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=f"invalid manifest: {e}")

    try:
        resolved = await resolve_draft(draft)
    except ResolverError as e:
        # Distinguish "manifest names something nonexistent" (caller fault → 422)
        # from "upstream registry is down" (operator concern → 502).
        if e.is_upstream_outage:
            raise HTTPException(status_code=502, detail=str(e))
        raise HTTPException(status_code=422, detail=str(e))

    manifest_dict = resolved.model_dump(mode="json")
    sha = sha256_of_manifest(manifest_dict)

    role = await session.scalar(
        _select_role_with_versions().where(RoleTemplate.slug == body.slug)
    )
    if role is None:
        role = RoleTemplate(
            slug=body.slug,
            display_name=body.display_name,
            description=body.description,
            kind=body.kind or "agent",
            tags=list(body.tags or []),
        )
        session.add(role)
        await session.flush()
        existing_versions: list[RoleTemplateVersion] = []
    else:
        role.display_name = body.display_name or role.display_name
        role.description = body.description or role.description
        # Only overwrite kind if the caller actually supplied one. Default
        # "agent" must never silently flip an existing kind="assistant" row.
        if body.kind is not None:
            role.kind = body.kind
        if body.tags:
            role.tags = list(body.tags)
        role.deleted_at = None
        existing_versions = list(role.versions)

    target_version = body.version
    if target_version is None:
        latest = _latest_row(existing_versions)
        target_version = _bump_patch(latest.version) if latest else "0.1.0"

    existing = next((v for v in existing_versions if v.version == target_version), None)
    if existing is not None:
        if existing.manifest_sha256 == sha:
            return RoleCreatedOut(
                slug=role.slug,
                version=existing.version,
                manifest_sha256=existing.manifest_sha256,
                manifest=existing.manifest,
                created_at=existing.created_at,
            )
        raise HTTPException(
            status_code=409,
            detail=f"version {target_version} already exists with different content",
        )

    rv = RoleTemplateVersion(
        role_template_id=role.id,
        version=target_version,
        manifest_sha256=sha,
        manifest=manifest_dict,
        created_by="admin",
    )
    session.add(rv)
    await session.commit()
    await session.refresh(rv)
    return RoleCreatedOut(
        slug=role.slug,
        version=rv.version,
        manifest_sha256=rv.manifest_sha256,
        manifest=rv.manifest,
        created_at=rv.created_at,
    )


@router.post("/roles/validate", response_model=RoleValidatedOut)
async def validate_role(
    body: RoleValidateIn,
    _: Annotated[str, Depends(require_admin_apikey)],
) -> RoleValidatedOut:
    """Dry-run a role manifest — same validation + resolver path as
    ``POST /api/admin/roles`` but never persists. Returns the resolved
    (skill/subagent versions pinned) manifest preview + its sha256, or
    422 with the validation/resolver error.

    Useful for AI-assisted editors that want to preview a manifest before
    asking the user to commit it.
    """
    try:
        draft = RoleManifestDraft(**body.manifest)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=f"invalid manifest: {e}")

    try:
        resolved = await resolve_draft(draft)
    except ResolverError as e:
        if e.is_upstream_outage:
            raise HTTPException(status_code=502, detail=str(e))
        raise HTTPException(status_code=422, detail=str(e))

    manifest_dict = resolved.model_dump(mode="json")
    return RoleValidatedOut(
        slug=body.slug,
        manifest_sha256=sha256_of_manifest(manifest_dict),
        manifest=manifest_dict,
    )


@router.delete("/roles/{slug}", status_code=204)
async def delete_role(
    slug: str,
    _: Annotated[str, Depends(require_admin_apikey)],
    session: AsyncSession = Depends(get_session),
) -> None:
    row = await session.scalar(select(RoleTemplate).where(RoleTemplate.slug == slug))
    if row is None:
        raise HTTPException(status_code=404, detail="role not found")
    row.deleted_at = datetime.now(timezone.utc)
    await session.commit()


@router.delete("/roles/{slug}/versions/{version}", status_code=204)
async def delete_role_version(
    slug: str,
    version: str,
    _: Annotated[str, Depends(require_admin_apikey)],
    session: AsyncSession = Depends(get_session),
) -> None:
    role = await session.scalar(select(RoleTemplate).where(RoleTemplate.slug == slug))
    if role is None:
        raise HTTPException(status_code=404, detail="role not found")
    rv = await session.scalar(
        select(RoleTemplateVersion).where(
            RoleTemplateVersion.role_template_id == role.id,
            RoleTemplateVersion.version == version,
        )
    )
    if rv is None:
        raise HTTPException(status_code=404, detail="version not found")
    await session.delete(rv)
    await session.commit()
