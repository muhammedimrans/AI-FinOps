"""EP-25.4: playground_executions table for AI Playground history

Adds a single new ``playground_executions`` table — the persisted history
for the AI Playground (prompt/response text, model params, tokens, cost,
latency). No existing table is touched. Every real usage/cost signal a
Playground request produces is written to the *existing*
UsageEvent/UsageCostRecord tables through the same repositories every
other usage-producing code path already uses (see
app/services/playground_service.py) — this table only adds the
prompt/response text and UI-facing history fields no existing table stores.

Revision ID: d1e2f3a4b5c6
Revises: c9d0e1f2a3b4
Create Date: 2026-07-12 09:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d1e2f3a4b5c6"
down_revision: str | None = "c9d0e1f2a3b4"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_STATUS_ENUM_NAME = "playground_execution_status"


def upgrade() -> None:
    status_enum = postgresql.ENUM(
        "succeeded", "failed", name=_STATUS_ENUM_NAME, create_type=False
    )
    status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "playground_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "organizations.id",
                ondelete="CASCADE",
                name="fk_playground_executions_organization_id",
            ),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_playground_executions_user_id"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "projects.id", ondelete="SET NULL", name="fk_playground_executions_project_id"
            ),
            nullable=True,
        ),
        sa.Column(
            "provider_connection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "provider_connections.id",
                ondelete="CASCADE",
                name="fk_playground_executions_provider_connection_id",
            ),
            nullable=False,
        ),
        sa.Column(
            "usage_event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "usage_events.id",
                ondelete="SET NULL",
                name="fk_playground_executions_usage_event_id",
            ),
            nullable=True,
        ),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=True),
        sa.Column("user_prompt", sa.Text(), nullable=False),
        sa.Column("response_text", sa.Text(), nullable=True),
        sa.Column("temperature", sa.Numeric(precision=4, scale=2), nullable=True),
        sa.Column("top_p", sa.Numeric(precision=4, scale=2), nullable=True),
        sa.Column("max_tokens", sa.Integer(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_cost", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("currency", sa.String(8), nullable=False, server_default="'USD'"),
        sa.Column("latency_ms", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("status", status_enum, nullable=False),
        sa.Column("error_message", sa.String(500), nullable=True),
        sa.Column("comparison_group_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("execution_metadata", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.create_index(
        "ix_playground_executions_cursor", "playground_executions", ["created_at", "id"]
    )
    op.create_index(
        "ix_playground_executions_deleted", "playground_executions", ["deleted_at"]
    )
    op.create_index(
        "ix_playground_executions_org_created",
        "playground_executions",
        ["organization_id", "created_at"],
    )
    op.create_index(
        "ix_playground_executions_user_created",
        "playground_executions",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_playground_executions_comparison_group",
        "playground_executions",
        ["comparison_group_id"],
    )


def downgrade() -> None:
    op.drop_table("playground_executions")
    postgresql.ENUM(name=_STATUS_ENUM_NAME).drop(op.get_bind(), checkfirst=True)
