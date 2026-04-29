from __future__ import annotations


import pytest
from sqlalchemy import select

from app.db import Base, get_engine, get_session_factory
from app.models import AgentEvent, ProvisionEvent, RoleTemplate, RoleTemplateVersion


@pytest.fixture
async def session():
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = get_session_factory()
    async with factory() as s:
        yield s
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def test_create_role_template_with_version(session):
    role = RoleTemplate(
        slug="support-agent",
        display_name="Support Lead",
        description="Handles customer support",
        kind="agent",
        tags=["support", "customer-facing"],
    )
    session.add(role)
    await session.flush()

    version = RoleTemplateVersion(
        role_template_id=role.id,
        version="0.1.0",
        manifest_sha256="a" * 64,
        manifest={"image": {"ref": "saac/support-agent", "version": "1.0.0"}},
        created_by="bootstrap",
    )
    session.add(version)
    await session.commit()

    fetched = (await session.execute(select(RoleTemplate).where(RoleTemplate.slug == "support-agent"))).scalar_one()
    assert fetched.display_name == "Support Lead"
    assert fetched.kind == "agent"
    assert "support" in fetched.tags

    fv = (await session.execute(select(RoleTemplateVersion))).scalar_one()
    assert fv.version == "0.1.0"
    assert fv.manifest["image"]["ref"] == "saac/support-agent"


async def test_role_template_version_unique_per_slug(session):
    role = RoleTemplate(slug="dup", kind="agent", tags=[])
    session.add(role)
    await session.flush()

    session.add(RoleTemplateVersion(
        role_template_id=role.id, version="0.1.0", manifest_sha256="x" * 64, manifest={},
    ))
    await session.commit()

    session.add(RoleTemplateVersion(
        role_template_id=role.id, version="0.1.0", manifest_sha256="y" * 64, manifest={},
    ))
    with pytest.raises(Exception):
        await session.commit()
    await session.rollback()


async def test_provision_event_records_outcome(session):
    pe = ProvisionEvent(
        role_slug="support-agent",
        role_version="0.1.0",
        organization_id="org-uuid",
        product_id="prod-uuid",
        agent_name="support-eu",
        agent_id_returned="agent-uuid",
        caller_token_fingerprint="abc123def456",
        variables={"SUPPORT_CHANNEL": "#eu-support"},
        integration_bindings=[{"catalog_slug": "zendesk", "connection_id": "conn-uuid"}],
        extra_skills=[],
        extra_subagents=[],
        status=200,
        error=None,
    )
    session.add(pe)
    await session.commit()
    fetched = (await session.execute(select(ProvisionEvent))).scalar_one()
    assert fetched.agent_id_returned == "agent-uuid"
    assert fetched.variables["SUPPORT_CHANNEL"] == "#eu-support"
    assert fetched.status == 200


async def test_agent_event_logs_action(session):
    ev = AgentEvent(
        action="list",
        token_fingerprint="abcd",
        remote_addr="127.0.0.1",
        user_agent="rolez-cli/0.1",
        status=200,
    )
    session.add(ev)
    await session.commit()
    fetched = (await session.execute(select(AgentEvent))).scalar_one()
    assert fetched.action == "list"
    assert fetched.status == 200
