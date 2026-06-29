"""EP-08: usage collection engine

Adds the tables required for the usage collection engine:
  - usage_collection_runs       : provider collection run records (F-041, F-042)
  - usage_events                : normalized per-request usage records (F-043, F-044)
  - usage_collection_checkpoints: incremental collection state (F-046)
  - provider_usage_summaries    : aggregated provider usage summaries (F-045)

All tables follow the standard BaseModel pattern:
  - UUID v7 primary key (id)
  - created_at, updated_at with server defaults
  - deleted_at, deleted_by for soft-delete
  - cursor index on (created_at, id) DESC for cursor pagination
  - deleted index on (deleted_at) for soft-delete filtering

Downgrade reverses all changes in strict reverse order.

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-06-29 08:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e6f7a8b9c0d1"
down_revision: str | None = "d5e6f7a8b9c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = postgresql.UUID(as_uuid=False)


def upgrade() -> None:
    # ── 1. usage_collection_runs ─────────────────────────────────────────────
    op.create_table(
        "usage_collection_runs",
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
        sa.Column("provider_connection_id", _UUID, nullable=True),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending", "running", "completed", "failed", "cancelled",
                name="collection_run_status",
            ),
            nullable=False,
        ),
        sa.Column(
            "triggered_by",
            sa.Enum("manual", "scheduled", name="collection_trigger"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("collection_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("collection_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("events_collected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("events_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pages_fetched", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "collection_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_usage_collection_runs_organization_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["provider_connection_id"],
            ["provider_connections.id"],
            name="fk_usage_collection_runs_provider_connection_id",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("external_id", name="uq_usage_collection_runs_external_id"),
    )
    op.create_index(
        "ix_usage_collection_runs_cursor",
        "usage_collection_runs",
        [sa.text("created_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "ix_usage_collection_runs_deleted",
        "usage_collection_runs",
        ["deleted_at"],
    )
    op.create_index(
        "ix_usage_collection_runs_organization_id",
        "usage_collection_runs",
        ["organization_id"],
    )
    op.create_index(
        "ix_usage_collection_runs_provider_connection_id",
        "usage_collection_runs",
        ["provider_connection_id"],
    )
    op.create_index(
        "ix_usage_collection_runs_provider",
        "usage_collection_runs",
        ["provider"],
    )
    op.create_index(
        "ix_usage_collection_runs_status",
        "usage_collection_runs",
        ["status"],
    )
    op.create_index(
        "ix_usage_collection_runs_org_provider",
        "usage_collection_runs",
        ["organization_id", "provider"],
    )
    op.create_index(
        "ix_usage_collection_runs_started_at",
        "usage_collection_runs",
        ["started_at"],
    )

    # ── 2. usage_events ──────────────────────────────────────────────────────
    op.create_table(
        "usage_events",
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
        sa.Column("provider_connection_id", _UUID, nullable=True),
        sa.Column("collection_run_id", _UUID, nullable=True),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("provider_request_id", sa.String(255), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cached_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "raw_provider_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_usage_events_organization_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_usage_events_project_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["provider_connection_id"],
            ["provider_connections.id"],
            name="fk_usage_events_provider_connection_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["collection_run_id"],
            ["usage_collection_runs.id"],
            name="fk_usage_events_collection_run_id",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("external_id", name="uq_usage_events_external_id"),
        sa.UniqueConstraint(
            "organization_id",
            "provider",
            "provider_request_id",
            name="uq_usage_events_dedup",
        ),
    )
    op.create_index(
        "ix_usage_events_cursor",
        "usage_events",
        [sa.text("created_at DESC"), sa.text("id DESC")],
    )
    op.create_index("ix_usage_events_deleted", "usage_events", ["deleted_at"])
    op.create_index("ix_usage_events_organization_id", "usage_events", ["organization_id"])
    op.create_index("ix_usage_events_project_id", "usage_events", ["project_id"])
    op.create_index(
        "ix_usage_events_provider_connection_id",
        "usage_events",
        ["provider_connection_id"],
    )
    op.create_index("ix_usage_events_collection_run_id", "usage_events", ["collection_run_id"])
    op.create_index("ix_usage_events_provider", "usage_events", ["provider"])
    op.create_index("ix_usage_events_model", "usage_events", ["model"])
    op.create_index("ix_usage_events_timestamp", "usage_events", ["timestamp"])
    op.create_index(
        "ix_usage_events_org_provider_ts",
        "usage_events",
        ["organization_id", "provider", "timestamp"],
    )
    op.create_index(
        "ix_usage_events_org_model",
        "usage_events",
        ["organization_id", "model"],
    )

    # ── 3. usage_collection_checkpoints ─────────────────────────────────────
    op.create_table(
        "usage_collection_checkpoints",
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
        sa.Column("provider_connection_id", _UUID, nullable=True),
        sa.Column("last_run_id", _UUID, nullable=True),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("last_collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cursor", sa.String(1024), nullable=True),
        sa.Column("page_token", sa.String(1024), nullable=True),
        sa.Column(
            "sync_state",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_usage_collection_checkpoints_organization_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["provider_connection_id"],
            ["provider_connections.id"],
            name="fk_usage_collection_checkpoints_provider_connection_id",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["last_run_id"],
            ["usage_collection_runs.id"],
            name="fk_usage_collection_checkpoints_last_run_id",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "external_id", name="uq_usage_collection_checkpoints_external_id"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "provider",
            "provider_connection_id",
            name="uq_usage_checkpoints_org_provider_connection",
            deferrable=True,
            initially="DEFERRED",
        ),
    )
    op.create_index(
        "ix_usage_collection_checkpoints_cursor",
        "usage_collection_checkpoints",
        [sa.text("created_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "ix_usage_collection_checkpoints_deleted",
        "usage_collection_checkpoints",
        ["deleted_at"],
    )
    op.create_index(
        "ix_usage_collection_checkpoints_organization_id",
        "usage_collection_checkpoints",
        ["organization_id"],
    )
    op.create_index(
        "ix_usage_collection_checkpoints_provider_connection_id",
        "usage_collection_checkpoints",
        ["provider_connection_id"],
    )
    op.create_index(
        "ix_usage_collection_checkpoints_provider",
        "usage_collection_checkpoints",
        ["provider"],
    )
    op.create_index(
        "ix_usage_collection_checkpoints_org_provider",
        "usage_collection_checkpoints",
        ["organization_id", "provider"],
    )

    # ── 4. provider_usage_summaries ──────────────────────────────────────────
    op.create_table(
        "provider_usage_summaries",
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
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_requests", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "total_prompt_tokens", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column(
            "total_completion_tokens",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("total_cached_tokens", sa.BigInteger(), nullable=True),
        sa.Column(
            "total_tokens", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column("event_count", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_provider_usage_summaries_organization_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_provider_usage_summaries_project_id",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "external_id", name="uq_provider_usage_summaries_external_id"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "project_id",
            "provider",
            "model",
            "period_start",
            "period_end",
            name="uq_provider_usage_summaries",
        ),
    )
    op.create_index(
        "ix_provider_usage_summaries_cursor",
        "provider_usage_summaries",
        [sa.text("created_at DESC"), sa.text("id DESC")],
    )
    op.create_index(
        "ix_provider_usage_summaries_deleted",
        "provider_usage_summaries",
        ["deleted_at"],
    )
    op.create_index(
        "ix_provider_usage_summaries_organization_id",
        "provider_usage_summaries",
        ["organization_id"],
    )
    op.create_index(
        "ix_provider_usage_summaries_project_id",
        "provider_usage_summaries",
        ["project_id"],
    )
    op.create_index(
        "ix_provider_usage_summaries_provider",
        "provider_usage_summaries",
        ["provider"],
    )
    op.create_index(
        "ix_provider_usage_summaries_period",
        "provider_usage_summaries",
        ["period_start", "period_end"],
    )
    op.create_index(
        "ix_provider_usage_summaries_org_provider",
        "provider_usage_summaries",
        ["organization_id", "provider"],
    )


def downgrade() -> None:
    # Reverse order: summaries → checkpoints → events → runs
    op.drop_table("provider_usage_summaries")
    op.drop_table("usage_collection_checkpoints")
    op.drop_table("usage_events")
    op.drop_table("usage_collection_runs")
    # Drop enums created for usage_collection_runs
    op.execute("DROP TYPE IF EXISTS collection_run_status")
    op.execute("DROP TYPE IF EXISTS collection_trigger")
