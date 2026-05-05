"""drop provision_events

Provisioning was removed from rolez — tech.saac is the canonical place to
provision agents (via its CLI / MCP `create_agent` with `rolez_slug`).
Rolez is now a pure catalogue + admin CRUD library.

Revision ID: 0002
Revises: b5ece89bb9f7
Create Date: 2026-04-30
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0002_drop_provision_events"
down_revision = "b5ece89bb9f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_provision_events_ts", table_name="provision_events")
    op.drop_index("ix_provision_events_role_slug", table_name="provision_events")
    op.drop_index("ix_provision_events_organization_id", table_name="provision_events")
    op.drop_table("provision_events")


def downgrade() -> None:
    op.create_table(
        "provision_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("role_slug", sa.String(length=128), nullable=False),
        sa.Column("role_version", sa.String(length=64), nullable=False),
        sa.Column("organization_id", sa.String(length=64), nullable=True),
        sa.Column("product_id", sa.String(length=64), nullable=True),
        sa.Column("agent_name", sa.String(length=128), nullable=True),
        sa.Column("agent_id_returned", sa.String(length=64), nullable=True),
        sa.Column("caller_token_fingerprint", sa.String(length=16), nullable=True),
        sa.Column("variables", sa.JSON(), nullable=False),
        sa.Column("integration_bindings", sa.JSON(), nullable=False),
        sa.Column("extra_skills", sa.JSON(), nullable=False),
        sa.Column("extra_subagents", sa.JSON(), nullable=False),
        sa.Column("status", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_provision_events_organization_id", "provision_events", ["organization_id"])
    op.create_index("ix_provision_events_role_slug", "provision_events", ["role_slug"])
    op.create_index("ix_provision_events_ts", "provision_events", ["ts"])
