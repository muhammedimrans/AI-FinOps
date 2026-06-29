"""EP-09: Cost & Analytics Engine

Adds the tables required for the cost calculation and analytics engine:
  - model_pricing           : versioned pricing configuration per (provider, model)
  - usage_cost_records      : computed cost for one UsageEvent
  - daily_cost_summaries    : pre-aggregated daily cost totals

All tables follow the standard BaseModel pattern:
  - UUID v7 primary key (id)
  - created_at, updated_at with server defaults
  - deleted_at, deleted_by for soft-delete
  - cursor index on (created_at, id) for cursor pagination
  - deleted index on (deleted_at) for soft-delete filtering

Downgrade reverses all changes in strict reverse order.

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-06-29 09:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f7a8b9c0d1e2"
down_revision: str | None = "e6f7a8b9c0d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = postgresql.UUID(as_uuid=False)

# Precision constants
_PRICE_PER_TOKEN = sa.Numeric(precision=20, scale=10)  # price-per-token fields
_COMPUTED_COST = sa.Numeric(precision=20, scale=8)      # computed cost fields


def upgrade() -> None:
    # ── 1. model_pricing ────────────────────────────────────────────────────────
    op.create_table(
        "model_pricing",
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
        # Required: external_id (from UUIDMixin)
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="USD"),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        # Price-per-token fields (Numeric 20,10 for sub-cent precision)
        sa.Column("prompt_token_price", _PRICE_PER_TOKEN, nullable=False),
        sa.Column("completion_token_price", _PRICE_PER_TOKEN, nullable=False),
        sa.Column("cached_token_price", _PRICE_PER_TOKEN, nullable=True),
        sa.Column("audio_token_price", _PRICE_PER_TOKEN, nullable=True),
        sa.Column("image_price", _PRICE_PER_TOKEN, nullable=True),
        sa.Column("embedding_price", _PRICE_PER_TOKEN, nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("notes", sa.Text(), nullable=True),
        # UniqueConstraint
        sa.UniqueConstraint("provider", "model", "version", name="uq_model_pricing_provider_model_version"),
    )
    # Indexes
    op.create_index("ix_model_pricing_provider_model_date", "model_pricing", ["provider", "model", "effective_from"])
    op.create_index("ix_model_pricing_provider_model_active", "model_pricing", ["provider", "model", "is_active"])
    op.create_index("ix_model_pricing_effective_range", "model_pricing", ["effective_from", "effective_to"])
    op.create_index("ix_model_pricing_cursor", "model_pricing", ["created_at", "id"])
    op.create_index("ix_model_pricing_deleted", "model_pricing", ["deleted_at"])

    # ── 2. usage_cost_records ────────────────────────────────────────────────────
    op.create_table(
        "usage_cost_records",
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
        # FK references
        sa.Column("usage_event_id", _UUID, nullable=False),
        sa.Column("organization_id", _UUID, nullable=False),
        sa.Column("project_id", _UUID, nullable=True),
        sa.Column("provider_connection_id", _UUID, nullable=True),
        sa.Column("model_pricing_id", _UUID, nullable=True),
        # Denormalized info
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("usage_date", sa.Date(), nullable=False),
        # Token counts
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cached_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        # Computed costs
        sa.Column("prompt_cost", _COMPUTED_COST, nullable=False),
        sa.Column("completion_cost", _COMPUTED_COST, nullable=False),
        sa.Column("cached_cost", _COMPUTED_COST, nullable=True),
        sa.Column("total_cost", _COMPUTED_COST, nullable=False),
        sa.Column("calculation_version", sa.String(32), nullable=False, server_default="1.0"),
        # FK constraints
        sa.ForeignKeyConstraint(
            ["usage_event_id"], ["usage_events.id"],
            ondelete="CASCADE",
            name="fk_usage_cost_records_usage_event_id",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            ondelete="CASCADE",
            name="fk_usage_cost_records_organization_id",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"],
            ondelete="SET NULL",
            name="fk_usage_cost_records_project_id",
        ),
        sa.ForeignKeyConstraint(
            ["provider_connection_id"], ["provider_connections.id"],
            ondelete="SET NULL",
            name="fk_usage_cost_records_connection_id",
        ),
        sa.ForeignKeyConstraint(
            ["model_pricing_id"], ["model_pricing.id"],
            ondelete="SET NULL",
            name="fk_usage_cost_records_model_pricing_id",
        ),
        # UniqueConstraint
        sa.UniqueConstraint("usage_event_id", name="uq_usage_cost_records_event"),
    )
    # Indexes
    op.create_index("ix_usage_cost_records_org_date", "usage_cost_records", ["organization_id", "usage_date"])
    op.create_index("ix_usage_cost_records_org_provider_date", "usage_cost_records", ["organization_id", "provider", "usage_date"])
    op.create_index("ix_usage_cost_records_org_project_date", "usage_cost_records", ["organization_id", "project_id", "usage_date"])
    op.create_index("ix_usage_cost_records_org_model_date", "usage_cost_records", ["organization_id", "model", "usage_date"])
    op.create_index("ix_usage_cost_records_pricing_id", "usage_cost_records", ["model_pricing_id"])
    op.create_index("ix_usage_cost_records_cursor", "usage_cost_records", ["created_at", "id"])
    op.create_index("ix_usage_cost_records_deleted", "usage_cost_records", ["deleted_at"])

    # ── 3. daily_cost_summaries ──────────────────────────────────────────────────
    op.create_table(
        "daily_cost_summaries",
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
        # Dimension keys
        sa.Column("organization_id", _UUID, nullable=False),
        sa.Column("project_id", _UUID, nullable=True),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("summary_date", sa.Date(), nullable=False),
        # Aggregated token counts
        sa.Column("total_prompt_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("total_completion_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("total_cached_tokens", sa.BigInteger(), nullable=True),
        sa.Column("total_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("total_requests", sa.Integer(), nullable=False, server_default="0"),
        # Aggregated costs
        sa.Column("total_cost", _COMPUTED_COST, nullable=False),
        sa.Column("total_prompt_cost", _COMPUTED_COST, nullable=False),
        sa.Column("total_completion_cost", _COMPUTED_COST, nullable=False),
        sa.Column("total_cached_cost", _COMPUTED_COST, nullable=True),
        sa.Column("event_count", sa.Integer(), nullable=False, server_default="0"),
        # FK constraints
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            ondelete="CASCADE",
            name="fk_daily_cost_summaries_organization_id",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"],
            ondelete="SET NULL",
            name="fk_daily_cost_summaries_project_id",
        ),
        # UniqueConstraint
        sa.UniqueConstraint(
            "organization_id", "project_id", "provider", "model", "currency", "summary_date",
            name="uq_daily_cost_summaries",
        ),
    )
    # Indexes
    op.create_index("ix_daily_cost_summaries_org_date", "daily_cost_summaries", ["organization_id", "summary_date"])
    op.create_index("ix_daily_cost_summaries_org_provider_date", "daily_cost_summaries", ["organization_id", "provider", "summary_date"])
    op.create_index("ix_daily_cost_summaries_org_project_date", "daily_cost_summaries", ["organization_id", "project_id", "summary_date"])
    op.create_index("ix_daily_cost_summaries_date", "daily_cost_summaries", ["summary_date"])
    op.create_index("ix_daily_cost_summaries_cursor", "daily_cost_summaries", ["created_at", "id"])
    op.create_index("ix_daily_cost_summaries_deleted", "daily_cost_summaries", ["deleted_at"])


def downgrade() -> None:
    # Drop in reverse order (child tables first)
    op.drop_index("ix_daily_cost_summaries_deleted", table_name="daily_cost_summaries")
    op.drop_index("ix_daily_cost_summaries_cursor", table_name="daily_cost_summaries")
    op.drop_index("ix_daily_cost_summaries_date", table_name="daily_cost_summaries")
    op.drop_index("ix_daily_cost_summaries_org_project_date", table_name="daily_cost_summaries")
    op.drop_index("ix_daily_cost_summaries_org_provider_date", table_name="daily_cost_summaries")
    op.drop_index("ix_daily_cost_summaries_org_date", table_name="daily_cost_summaries")
    op.drop_table("daily_cost_summaries")

    op.drop_index("ix_usage_cost_records_deleted", table_name="usage_cost_records")
    op.drop_index("ix_usage_cost_records_cursor", table_name="usage_cost_records")
    op.drop_index("ix_usage_cost_records_pricing_id", table_name="usage_cost_records")
    op.drop_index("ix_usage_cost_records_org_model_date", table_name="usage_cost_records")
    op.drop_index("ix_usage_cost_records_org_project_date", table_name="usage_cost_records")
    op.drop_index("ix_usage_cost_records_org_provider_date", table_name="usage_cost_records")
    op.drop_index("ix_usage_cost_records_org_date", table_name="usage_cost_records")
    op.drop_table("usage_cost_records")

    op.drop_index("ix_model_pricing_deleted", table_name="model_pricing")
    op.drop_index("ix_model_pricing_cursor", table_name="model_pricing")
    op.drop_index("ix_model_pricing_effective_range", table_name="model_pricing")
    op.drop_index("ix_model_pricing_provider_model_active", table_name="model_pricing")
    op.drop_index("ix_model_pricing_provider_model_date", table_name="model_pricing")
    op.drop_table("model_pricing")
