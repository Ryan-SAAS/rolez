from __future__ import annotations

import copy
import hashlib
import logging
from dataclasses import dataclass
from typing import Any

from packaging.version import InvalidVersion, Version
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.clients.techsaac import (
    TechsaacClient,
    TechsaacError,
    TechsaacHTTPError,
    TechsaacProtocolError,
    TechsaacRPCError,
    TechsaacUnreachable,
)
from app.config import get_settings
from app.models import ProvisionEvent, RoleTemplate, RoleTemplateVersion

log = logging.getLogger(__name__)


class ProvisionError(Exception):
    def __init__(self, message: str, status_code: int = 500, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


CREATE_AGENT_TOOL = "create_agent"


@dataclass(frozen=True, slots=True)
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
    if not role.versions:
        raise ProvisionError("role has no published versions", status_code=404)

    if version in (None, "", "latest"):
        try:
            rv = max(role.versions, key=lambda v: Version(v.version))
        except InvalidVersion:
            # Some row in role.versions has a version string that isn't valid
            # semver. Don't silently fall through to versions[0] — that would
            # let a corrupt row downgrade every "latest" provision. Log loudly
            # and refuse to guess.
            bad = [v.version for v in role.versions]
            log.error(
                "role %s has non-semver versions %r — refusing to resolve 'latest'",
                slug, bad,
            )
            raise ProvisionError(
                f"role {slug!r} has unparseable version strings — pin an explicit version",
                status_code=409,
            )
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


def _extract_agent_id(result: Any) -> str | None:
    """Look for the new agent's id in the two shapes tech.saac is known to
    return. Returns None if neither matches — caller treats that as a
    contract drift, not a successful provision."""
    if not isinstance(result, dict):
        return None
    agent_id = result.get("agent_id")
    if agent_id:
        return str(agent_id)
    agent = result.get("agent")
    if isinstance(agent, dict):
        nested = agent.get("id") or agent.get("agent_id")
        if nested:
            return str(nested)
    return None


async def provision(
    session: AsyncSession,
    *,
    slug: str,
    payload: dict,
    caller_token: str,
) -> dict:
    """Provision an agent of the given role. Calls tech.saac with the caller's
    token; records a ``ProvisionEvent`` for every attempted call (success,
    validation failure, or upstream failure)."""
    version_req = payload.get("version", "latest")
    organization_id = payload.get("organization_id")
    product_id = payload.get("product_id")
    name = payload.get("name")
    variables = payload.get("variables") or {}
    integration_bindings = payload.get("integration_bindings") or []
    extra_skills = payload.get("extra_skills") or []
    extra_subagents = payload.get("extra_subagents") or []

    fp = _token_fingerprint(caller_token)

    # _resolve_role raises ProvisionError(404) for missing role / version /
    # versions list. We let it propagate without persisting a provision_event
    # — nothing was attempted.
    resolved = await _resolve_role(session, slug, version_req)

    base_manifest = copy.deepcopy(resolved.rv.manifest)
    base_manifest["skills"] = _merge_extras(base_manifest.get("skills") or [], extra_skills)
    base_manifest["subagents"] = _merge_extras(base_manifest.get("subagents") or [], extra_subagents)

    def record(*, status_code: int, error: str | None, agent_id_returned: str | None = None) -> None:
        session.add(ProvisionEvent(
            role_slug=slug,
            role_version=resolved.rv.version,
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
        ))

    try:
        _validate_required_variables(base_manifest, variables)
    except ProvisionError as e:
        record(status_code=e.status_code, error=str(e))
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
    except TechsaacUnreachable as e:
        record(status_code=503, error=str(e))
        await session.commit()
        raise ProvisionError(str(e), status_code=503, body=e.body) from e
    except TechsaacHTTPError as e:
        # Relay tech.saac's own status code verbatim (401 stays 401, 403 stays 403).
        status_code = e.status_code or 502
        record(status_code=status_code, error=str(e))
        await session.commit()
        raise ProvisionError(str(e), status_code=status_code, body=e.body) from e
    except (TechsaacRPCError, TechsaacProtocolError) as e:
        # JSON-RPC error or non-JSON body — transport returned 200 but the
        # tool failed. We can't trust the upstream's intent, so 502.
        record(status_code=502, error=str(e))
        await session.commit()
        raise ProvisionError(str(e), status_code=502, body=e.body) from e
    except TechsaacError as e:
        record(status_code=502, error=str(e))
        await session.commit()
        raise ProvisionError(str(e), status_code=502, body=e.body) from e

    agent_id = _extract_agent_id(result)
    if agent_id is None:
        # Transport said 200 but neither shape we know about carries an
        # agent_id. Treat as protocol drift — record and surface 502 so the
        # caller and the audit log both see the failure.
        keys = sorted(result.keys()) if isinstance(result, dict) else type(result).__name__
        msg = f"tech.saac create_agent returned no recognizable agent id (got keys={keys!r})"
        log.error(msg)
        record(status_code=502, error=msg)
        await session.commit()
        raise ProvisionError(msg, status_code=502, body=result)

    record(status_code=200, error=None, agent_id_returned=agent_id)
    await session.commit()

    return {
        "agent_id": agent_id,
        "role_slug": slug,
        "role_version": resolved.rv.version,
        "status": 200,
        "tech_saac_response": result,
    }
