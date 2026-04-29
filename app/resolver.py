from __future__ import annotations

from app.clients.agentz import AgentzClient, AgentzError, AgentzNotFound, AgentzUnreachable
from app.clients.skillz import SkillzClient, SkillzError, SkillzNotFound, SkillzUnreachable
from app.config import get_settings
from app.validation import (
    ImageRefDraft,
    RoleManifestDraft,
    SkillRefDraft,
    SubagentRefDraft,
    validate_version,
)


class ResolverError(Exception):
    """A skill/subagent reference could not be resolved.

    `is_upstream_outage=True` means the upstream registry was reachable-but-broken
    (5xx, network), as opposed to a 404 (the manifest names something that
    doesn't exist). Callers in the admin router map this to 502 vs 422
    respectively, so admin sees an honest signal of where the failure is.
    """

    def __init__(self, message: str, *, is_upstream_outage: bool = False):
        super().__init__(message)
        self.is_upstream_outage = is_upstream_outage


def _build_skillz() -> SkillzClient:
    s = get_settings()
    return SkillzClient(base_url=s.skillz_api_url, token=s.skillz_token)


def _build_agentz() -> AgentzClient:
    s = get_settings()
    return AgentzClient(base_url=s.agentz_api_url, token=s.agentz_token)


async def _resolve_skill_version(
    client: SkillzClient, ref: SkillRefDraft
) -> SkillRefDraft:
    if ref.version != "latest":
        return ref
    try:
        data = await client.get_skill(ref.name)
    except SkillzNotFound as e:
        raise ResolverError(str(e)) from e
    except SkillzUnreachable as e:
        raise ResolverError(
            f"skillz outage while resolving {ref.name!r}: {e}",
            is_upstream_outage=True,
        ) from e
    except SkillzError as e:
        raise ResolverError(f"failed to resolve skill {ref.name!r}: {e}") from e
    latest = data.get("latest_version")
    if not latest:
        raise ResolverError(f"skill {ref.name!r} has no published versions")
    validate_version(latest)
    return SkillRefDraft(name=ref.name, version=latest)


async def _resolve_subagent_version(
    client: AgentzClient, ref: SubagentRefDraft
) -> SubagentRefDraft:
    if ref.version != "latest":
        return ref
    try:
        data = await client.get_agent(ref.name)
    except AgentzNotFound as e:
        raise ResolverError(str(e)) from e
    except AgentzUnreachable as e:
        raise ResolverError(
            f"agentz outage while resolving {ref.name!r}: {e}",
            is_upstream_outage=True,
        ) from e
    except AgentzError as e:
        raise ResolverError(f"failed to resolve subagent {ref.name!r}: {e}") from e
    latest = data.get("latest_version")
    if not latest:
        raise ResolverError(f"subagent {ref.name!r} has no published versions")
    validate_version(latest)
    return SubagentRefDraft(name=ref.name, version=latest)


async def _resolve_image(image: ImageRefDraft) -> ImageRefDraft:
    """The image ref is forwarded verbatim — concrete digest resolution
    happens inside tech.saac's `create_agent` tool at provision time. Rolez
    does not (yet) consult an image catalog, so `latest` is preserved here."""
    return image


async def resolve_draft(draft: RoleManifestDraft) -> RoleManifestDraft:
    """Resolve `latest` skill/subagent refs to pinned versions.

    The resolved manifest is still typed as RoleManifestDraft (which accepts
    pinned versions natively); we don't promote it to RoleManifest because
    the image ref may stay deferred.
    """
    skillz = _build_skillz()
    agentz = _build_agentz()
    skills = [await _resolve_skill_version(skillz, s) for s in draft.skills]
    subagents = [await _resolve_subagent_version(agentz, a) for a in draft.subagents]
    image = await _resolve_image(draft.image)
    return draft.model_copy(update={"skills": skills, "subagents": subagents, "image": image})
