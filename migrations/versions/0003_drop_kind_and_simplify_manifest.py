"""drop kind column + simplify manifest JSON

Schema-wise the only column drop is ``role_templates.kind``. The bigger
change is a one-time data migration on ``role_template_versions.manifest``:

  - drop the ``identity`` block (display_name on the row covers it)
  - drop ``context_files: [{name, content}]`` array
  - extract ``context_files[name='CLAUDE.md'].content`` → top-level
    ``context: str`` field (other context_files entries are discarded —
    tech.saac's daemon-config builder only ever read the CLAUDE.md one)

This is a breaking API change; rolez bumps to 0.2.0 to signal it.

Revision ID: 0003_simplify_manifest
Revises: 0002_drop_provision_events
Create Date: 2026-05-06

Note on revision-ID length: ``alembic_version.version_num`` is the
Alembic default VARCHAR(32). The previous ID for this migration
(``0003_drop_kind_and_simplify_manifest``, 36 chars) overflowed that
column and rolled back the whole transaction on Railway's Postgres,
even though the DDL + data step both ran fine. Keep new revision IDs
≤ 32 chars (the actual filename can still be longer).
"""
from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa


revision = "0003_simplify_manifest"
down_revision = "0002_drop_provision_events"
branch_labels = None
depends_on = None


def _flatten_manifest(manifest: dict) -> dict:
    """Strip identity + context_files, fold CLAUDE.md content into context."""
    out = {k: v for k, v in (manifest or {}).items() if k not in ("identity", "context_files")}
    context = ""
    for entry in (manifest or {}).get("context_files") or []:
        if isinstance(entry, dict) and entry.get("name") == "CLAUDE.md":
            context = entry.get("content") or ""
            break
    out["context"] = context
    return out


def upgrade() -> None:
    # 1. Drop kind column from role_templates.
    op.drop_column("role_templates", "kind")

    # 2. Flatten every existing manifest JSON in role_template_versions.
    # Use the bind directly — Alembic batch_op isn't needed for an UPDATE.
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, manifest FROM role_template_versions")).fetchall()
    for row in rows:
        rid = row[0]
        raw = row[1]
        manifest = raw if isinstance(raw, dict) else json.loads(raw or "{}")
        flat = _flatten_manifest(manifest)
        bind.execute(
            sa.text("UPDATE role_template_versions SET manifest = :m WHERE id = :i"),
            {"m": json.dumps(flat), "i": rid},
        )


def downgrade() -> None:
    # Re-add kind column with default 'agent'.
    op.add_column(
        "role_templates",
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="agent"),
    )
    # Manifest reshape on downgrade is not attempted — the flattening was
    # lossy (identity + non-CLAUDE.md context_files were discarded). Callers
    # who need the old shape should restore from a pre-0003 backup.
