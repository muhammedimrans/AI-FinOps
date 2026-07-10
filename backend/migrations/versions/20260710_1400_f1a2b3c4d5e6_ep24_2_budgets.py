"""EP-24.2: budgets table for proactive spend alerts

Adds a single new ``budgets`` table — the first-class, multi-scope
(organization/project/provider/model), multi-threshold, period-aware
budget entity EP-24.2 introduces. This is additive: the pre-existing
``projects.budget`` column (EP-19.3) and its ingest-time budget check are
left completely unchanged (see CLAUDE.md's EP-24.2 section for why both
coexist).

Revision ID: f1a2b3c4d5e6
Revises: e8f1a2b3c4d5
Create Date: 2026-07-10 14:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: str | None = "e8f1a2b3c4d5"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    budget_scope_type = postgresql.ENUM(
        "organization", "project", "provider", "model", name="budget_scope_type", create_type=True
    )
    budget_period = postgresql.ENUM(
        "daily", "weekly", "monthly", "yearly", "custom", name="budget_period", create_type=True
    )
    bind = op.get_bind()
    budget_scope_type.create(bind, checkfirst=True)
    budget_period.create(bind, checkfirst=True)

    op.create_table(
        "budgets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("scope_type", budget_scope_type, nullable=False),
        sa.Column("scope_project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("scope_provider", sa.String(length=64), nullable=True),
        sa.Column("scope_model", sa.String(length=128), nullable=True),
        sa.Column("amount", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="USD"),
        sa.Column("period", budget_period, nullable=False),
        sa.Column("custom_period_start", sa.Date(), nullable=True),
        sa.Column("custom_period_end", sa.Date(), nullable=True),
        sa.Column(
            "threshold_percentages",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[50, 75, 90, 100]",
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_budgets_organization_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["scope_project_id"],
            ["projects.id"],
            name="fk_budgets_scope_project_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="fk_budgets_created_by", ondelete="SET NULL"
        ),
    )

    op.create_index("ix_budgets_cursor", "budgets", ["created_at", "id"])
    op.create_index("ix_budgets_deleted", "budgets", ["deleted_at"])
    op.create_index("ix_budgets_org_id", "budgets", ["organization_id"])
    op.create_index("ix_budgets_org_enabled", "budgets", ["organization_id", "enabled"])
    op.create_index("ix_budgets_org_scope_type", "budgets", ["organization_id", "scope_type"])
    op.create_index("ix_budgets_scope_project_id", "budgets", ["scope_project_id"])


def downgrade() -> None:
    op.drop_index("ix_budgets_scope_project_id", table_name="budgets")
    op.drop_index("ix_budgets_org_scope_type", table_name="budgets")
    op.drop_index("ix_budgets_org_enabled", table_name="budgets")
    op.drop_index("ix_budgets_org_id", table_name="budgets")
    op.drop_index("ix_budgets_deleted", table_name="budgets")
    op.drop_index("ix_budgets_cursor", table_name="budgets")
    op.drop_table("budgets")

    bind = op.get_bind()
    postgresql.ENUM(name="budget_period").drop(bind, checkfirst=True)
    postgresql.ENUM(name="budget_scope_type").drop(bind, checkfirst=True)
