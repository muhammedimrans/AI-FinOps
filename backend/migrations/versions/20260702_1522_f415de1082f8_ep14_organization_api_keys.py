"""EP-14: organization API keys (Phase 1)

Adds organization_api_keys — programmatic API keys scoped to one
organization. Follows the standard BaseModel pattern:
  - UUID v7 primary key (id)
  - created_at, updated_at with server defaults
  - deleted_at, deleted_by for soft-delete
  - cursor index on (created_at, id) for cursor pagination
  - deleted index on (deleted_at) for soft-delete filtering

The raw key is never stored — only a SHA-256 hash (key_hash, unique) and a
short non-secret display prefix (key_prefix).

Revision ID: f415de1082f8
Revises: f7a8b9c0d1e2
Create Date: 2026-07-02 15:22:54.851333
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f415de1082f8"
down_revision: str | None = "f7a8b9c0d1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = postgresql.UUID(as_uuid=False)


def upgrade() -> None:
    op.create_table(
        "organization_api_keys",
        sa.Column("id", _UUID, primary_key=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", _UUID, nullable=True),
        sa.Column("external_id", sa.String(64), nullable=False),
        sa.Column("organization_id", _UUID, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("key_prefix", sa.String(32), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column(
            "permissions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("created_by", _UUID, nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_organization_api_keys_organization_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_organization_api_keys_created_by",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("external_id", name="uq_organization_api_keys_external_id"),
    )
    op.create_index(
        "ix_organization_api_keys_cursor",
        "organization_api_keys",
        [sa.text("created_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "ix_organization_api_keys_deleted",
        "organization_api_keys",
        ["deleted_at"],
    )
    op.create_index(
        "ix_organization_api_keys_organization_id",
        "organization_api_keys",
        ["organization_id"],
    )
    op.create_index(
        "ix_organization_api_keys_key_hash",
        "organization_api_keys",
        ["key_hash"],
        unique=True,
    )
    op.create_index(
        "ix_organization_api_keys_created_by",
        "organization_api_keys",
        ["created_by"],
    )


def downgrade() -> None:
    op.drop_table("organization_api_keys")
