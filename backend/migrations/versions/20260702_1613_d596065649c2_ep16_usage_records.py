"""EP-16: usage_records (usage ingestion ledger)

Adds usage_records — one row per ingested POST /v1/ingest/usage call.
Follows the standard BaseModel pattern:
  - UUID v7 primary key (id)
  - created_at, updated_at with server defaults
  - deleted_at, deleted_by for soft-delete
  - cursor index on (created_at, id) DESC for cursor pagination
  - deleted index on (deleted_at) for soft-delete filtering

Idempotency is enforced by a unique constraint on
(organization_id, request_id) — the database, not just application logic,
guarantees a duplicate request_id can never create a second row.

Revision ID: d596065649c2
Revises: e2b8f387cc86
Create Date: 2026-07-02 16:13:50.235255
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d596065649c2"
down_revision: str | None = "e2b8f387cc86"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = postgresql.UUID(as_uuid=False)


def upgrade() -> None:
    op.create_table(
        "usage_records",
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
        sa.Column("project_id", _UUID, nullable=True),
        sa.Column("api_key_id", _UUID, nullable=True),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("request_id", sa.String(512), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "success", "error", "timeout", "cancelled",
                name="usage_record_status",
            ),
            nullable=False,
        ),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cached_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="USD"),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("region", sa.String(64), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_usage_records_organization_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_usage_records_project_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["api_key_id"],
            ["organization_api_keys.id"],
            name="fk_usage_records_api_key_id",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("external_id", name="uq_usage_records_external_id"),
        sa.UniqueConstraint(
            "organization_id", "request_id", name="uq_usage_records_org_request_id"
        ),
    )
    op.create_index(
        "ix_usage_records_cursor",
        "usage_records",
        [sa.text("created_at DESC"), sa.text("id DESC")],
    )
    op.create_index("ix_usage_records_deleted", "usage_records", ["deleted_at"])
    op.create_index(
        "ix_usage_records_organization_id", "usage_records", ["organization_id"]
    )
    op.create_index("ix_usage_records_project_id", "usage_records", ["project_id"])
    op.create_index("ix_usage_records_api_key_id", "usage_records", ["api_key_id"])
    op.create_index("ix_usage_records_provider", "usage_records", ["provider"])
    op.create_index("ix_usage_records_model", "usage_records", ["model"])
    op.create_index("ix_usage_records_status", "usage_records", ["status"])
    op.create_index(
        "ix_usage_records_request_timestamp", "usage_records", ["request_timestamp"]
    )
    op.create_index(
        "ix_usage_records_org_provider_ts",
        "usage_records",
        ["organization_id", "provider", "request_timestamp"],
    )
    op.create_index(
        "ix_usage_records_org_model_ts",
        "usage_records",
        ["organization_id", "model", "request_timestamp"],
    )
    op.create_index(
        "ix_usage_records_org_project_ts",
        "usage_records",
        ["organization_id", "project_id", "request_timestamp"],
    )


def downgrade() -> None:
    op.drop_table("usage_records")
    op.execute("DROP TYPE IF EXISTS usage_record_status")
