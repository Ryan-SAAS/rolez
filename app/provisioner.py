from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass
from typing import Any

from packaging.version import InvalidVersion, Version
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.clients.techsaac import TechsaacClient, TechsaacError
from app.config import get_settings
from app.models import ProvisionEvent, RoleTemplate, RoleTemplateVersion


class ProvisionError(Exception):
    def __init__(self, message: str, status_code: int = 500, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


CREATE_AGENT_TOOL = "create_agent"


@dataclass
class _Resolved:
    role: RoleTemplate
    rv: RoleTemplateVersion


async def _resolve_role(
    session: AsyncSession, slug: str, version: str
) -> _Resolved:
    role = await session.scalar(
        select(RoleTemplate)
        .options(selectinload(RoleTemplate.versions))
        .where(RoleTemplate.slug == slug, RoleTemplate.deleted_at.is_(None))
    )
    if role is None:
        raise ProvisionError("role not found", status_code=404)
    if version in (None, "", "latest"):
        try:
            rv = max(role.versions, key=lambda v: Version(v.version))
        except (ValueError, InvalidVersion):
            if not role.versions:
                raise ProvisionError("role has no published versions", status_code=404)
            rv = role.versions[0]
    else:
        match = next((v for v in role.versions if v.version == version), None)
        if match is None:
            raise ProvisionError(f"version {version!r} not found", status_code=404)
        rv = match
    return _Resolved(role=role, rv=rv)


def _merge_extras(
    base: list[dict], extras: list[dict], key: str = "name"
) -> list[dict]:
    """Merge `extras` into `base`, deduping by key. Later entries win."""
    out: dict[str, dict] = {item[key]: dict(item) for item in base}
    for item in extras:
        out[item[key]] = dict(item)
    return list(out.values())


def _validate_required_variables(manifest: dict, supplied: dict[str, str]) -> None:
    required = manifest.get("required_variables") or []
    missing = [r["name"] for r in required if r["name"] not in supplied]
    if missing:
        raise ProvisionError(
            f"missing required variables: {', '.join(missing)}",
            status_code=422,
        )


def _token_fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]


async def provision(
    session: AsyncSession,
    *,
    slug: str,
    payload: dict,
    caller_token: str,
) -> dict:
    """Provision an agent of the given role. Calls tech.saac with the caller's
    token; records a ProvisionEvent regardless of outcome."""
    version_req = payload.get("version", "latest")
    organization_id = payload.get("organization_id")
    product_id = payload.get("product_id")
    name = payload.get("name")
    variables = payload.get("variables") or {}
    integration_bindings = payload.get("integration_bindings") or []
    extra_skills = payload.get("extra_skills") or []
    extra_subagents = payload.get("extra_subagents") or []

    fp = _token_fingerprint(caller_token)

    try:
        resolved = await _resolve_role(session, slug, version_req)
    except ProvisionError:
        # Don't log a provision_event for "role not found" — nothing was attempted.
        raise

    base_manifest = copy.deepcopy(resolved.rv.manifest)
    base_manifest["skills"] = _merge_extras(base_manifest.get("skills") or [], extra_skills)
    base_manifest["subagents"] = _merge_extras(base_manifest.get("subagents") or [], extra_subagents)

    try:
        _validate_required_variables(base_manifest, variables)
    except ProvisionError as e:
        session.add(_event_row(slug, resolved.rv.version, organization_id, product_id, name, fp,
                                variables, integration_bindings, extra_skills, extra_subagents,
                                status_code=e.status_code, error=str(e)))
        await session.commit()
        raise

    create_args = {
        "organization_id": organization_id,
        "product_id": product_id,
        "name": name,
        "role_slug": slug,
        "role_version": resolved.rv.version,
        "manifest": base_manifest,
        "variables": variables,
        "integration_bindings": integration_bindings,
    }

    settings = get_settings()
    client = TechsaacClient(base_url=settings.mcp_orchestrator_url)
    try:
        result = await client.call_tool(
            CREATE_AGENT_TOOL, create_args, caller_token=caller_token
        )
    except TechsaacError as e:
        status_code = e.status_code or 502
        body = e.body
        session.add(_event_row(slug, resolved.rv.version, organization_id, product_id, name, fp,
                                variables, integration_bindings, extra_skills, extra_subagents,
                                status_code=status_code, error=str(e)))
        await session.commit()
        raise ProvisionError(str(e), status_code=status_code, body=body) from e

    agent_id = None
    if isinstance(result, dict):
        agent_id = result.get("agent_id") or (result.get("agent") or {}).get("id")

    session.add(_event_row(slug, resolved.rv.version, organization_id, product_id, name, fp,
                            variables, integration_bindings, extra_skills, extra_subagents,
                            status_code=200, error=None, agent_id_returned=agent_id))
    await session.commit()

    return {
        "agent_id": agent_id,
        "role_slug": slug,
        "role_version": resolved.rv.version,
        "status": 200,
        "tech_saac_response": result,
    }


def _event_row(
    slug: str, version: str, organization_id, product_id, name: str | None, fp: str,
    variables: dict, integration_bindings: list, extra_skills: list, extra_subagents: list,
    *, status_code: int, error: str | None, agent_id_returned: str | None = None,
) -> ProvisionEvent:
    return ProvisionEvent(
        role_slug=slug,
        role_version=version,
        organization_id=str(organization_id) if organization_id else None,
        product_id=str(product_id) if product_id else None,
        agent_name=name,
        agent_id_returned=agent_id_returned,
        caller_token_fingerprint=fp,
        variables=dict(variables or {}),
        integration_bindings=list(integration_bindings or []),
        extra_skills=list(extra_skills or []),
        extra_subagents=list(extra_subagents or []),
        status=status_code,
        error=error,
    )
