from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class RoleTemplate(Base):
    __tablename__ = "role_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="agent")
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    versions: Mapped[list["RoleTemplateVersion"]] = relationship(
        back_populates="role_template",
        cascade="all, delete-orphan",
        order_by="RoleTemplateVersion.created_at.desc()",
    )


class RoleTemplateVersion(Base):
    __tablename__ = "role_template_versions"
    __table_args__ = (
        UniqueConstraint("role_template_id", "version", name="uq_role_template_versions_role_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role_template_id: Mapped[int] = mapped_column(
        ForeignKey("role_templates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    manifest: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)

    role_template: Mapped[RoleTemplate] = relationship(back_populates="versions")


class ProvisionEvent(Base):
    __tablename__ = "provision_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    role_slug: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    role_version: Mapped[str] = mapped_column(String(64), nullable=False)
    organization_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    product_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    agent_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    agent_id_returned: Mapped[str | None] = mapped_column(String(64), nullable=True)
    caller_token_fingerprint: Mapped[str | None] = mapped_column(String(16), nullable=True)
    variables: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    integration_bindings: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    extra_skills: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    extra_subagents: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[int] = mapped_column(Integer, nullable=False, default=200)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class AgentEvent(Base):
    __tablename__ = "agent_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    role_slug: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    token_fingerprint: Mapped[str | None] = mapped_column(String(16), nullable=True)
    remote_addr: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(256), nullable=True)
    status: Mapped[int] = mapped_column(Integer, nullable=False, default=200)
