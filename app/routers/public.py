from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from packaging.version import InvalidVersion, Version
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import extract_apikey, token_fingerprint
from app.db import get_session
from app.models import RoleTemplate, RoleTemplateVersion
from app.schemas import RoleListOut, RoleOut, RoleVersionOut
from app.upstream_auth import UpstreamUnreachable, verify_token

router = APIRouter(prefix="/api/v1", tags=["public"])

log = logging.getLogger(__name__)


def _select_role_with_versions():
    return select(RoleTemplate).options(selectinload(RoleTemplate.versions))


async def require_caller_token(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    """Extract the caller's tech.saac MCP api key and verify it upstream."""
    token = extract_apikey(authorization)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing api key",
        )
    try:
        ok = await verify_token(token)
    except UpstreamUnreachable as e:
        # Log the detail server-side; do NOT echo upstream URLs / connect-error
        # internals to unauthenticated callers.
        log.error("upstream auth probe failed: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="upstream auth unavailable",
        )
    if not ok:
        log.info("upstream rejected token fp=%s", token_fingerprint(token))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid api key",
        )
    return token


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


@router.get("/roles", response_model=RoleListOut)
async def list_roles(
    _token: Annotated[str, Depends(require_caller_token)],
    session: AsyncSession = Depends(get_session),
    tag: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> RoleListOut:
    stmt = _select_role_with_versions().where(RoleTemplate.deleted_at.is_(None))
    if kind:
        stmt = stmt.where(RoleTemplate.kind == kind)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(RoleTemplate.slug.ilike(like), RoleTemplate.description.ilike(like)))
    rows = (await session.execute(stmt.order_by(RoleTemplate.slug))).scalars().all()
    if tag:
        rows = [r for r in rows if tag in (r.tags or [])]
    # `total` is the unpaginated count (post-filter) so callers can size pagers.
    total = len(rows)
    items = [_to_role_out(r) for r in rows[offset : offset + limit]]
    return RoleListOut(total=total, items=items)


@router.get("/roles/search", response_model=RoleListOut)
async def search_roles(
    _token: Annotated[str, Depends(require_caller_token)],
    q: str = Query(..., min_length=1),
    session: AsyncSession = Depends(get_session),
) -> RoleListOut:
    like = f"%{q}%"
    stmt = (
        _select_role_with_versions()
        .where(
            RoleTemplate.deleted_at.is_(None),
            or_(RoleTemplate.slug.ilike(like), RoleTemplate.description.ilike(like)),
        )
        .order_by(RoleTemplate.slug)
    )
    rows = (await session.execute(stmt)).scalars().all()
    items = [_to_role_out(r) for r in rows]
    return RoleListOut(total=len(items), items=items)


@router.get("/roles/{slug}")
async def show_role(
    slug: str,
    _token: Annotated[str, Depends(require_caller_token)],
    session: AsyncSession = Depends(get_session),
) -> dict:
    role = await session.scalar(
        _select_role_with_versions().where(
            RoleTemplate.slug == slug, RoleTemplate.deleted_at.is_(None)
        )
    )
    if role is None:
        raise HTTPException(status_code=404, detail="role not found")
    latest = _latest_row(list(role.versions))
    return {
        **_to_role_out(role).model_dump(),
        "manifest": latest.manifest if latest else None,
        "manifest_sha256": latest.manifest_sha256 if latest else None,
        "versions": [RoleVersionOut.model_validate(v).model_dump() for v in role.versions],
    }


@router.get("/roles/{slug}/versions/{version}")
async def show_role_version(
    slug: str,
    version: str,
    _token: Annotated[str, Depends(require_caller_token)],
    session: AsyncSession = Depends(get_session),
) -> dict:
    role = await session.scalar(
        _select_role_with_versions().where(
            RoleTemplate.slug == slug, RoleTemplate.deleted_at.is_(None)
        )
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
