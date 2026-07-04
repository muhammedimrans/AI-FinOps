"""EP-03: core domain models

Creates the four foundational business entities:
  - organizations
  - projects
  - memberships
  - provider_connections

Revision ID: a3b4c5d6e7f8
Revises: 09c89dba8c85
Create Date: 2026-06-29 02:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a3b4c5d6e7f8"
down_revision: str | None = "09c89dba8c85"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ── Enum helpers ──────────────────────────────────────────────────────────────

_org_status = postgresql.ENUM(
    "active", "suspended", "archived",
    name="organization_status",
    create_type=False,
)
_proj_env = postgresql.ENUM(
    "development", "staging", "production",
    name="project_environment",
    create_type=False,
)
_mem_role = postgresql.ENUM(
    "owner", "admin", "member", "viewer",
    name="membership_role",
    create_type=False,
)
_prov_type = postgresql.ENUM(
    "openai", "anthropic", "grok", "google", "azure_openai", "openrouter", "ollama",
    name="provider_type",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()

    # ── Create enum types ─────────────────────────────────────────────────────
    _org_status.create(bind, checkfirst=True)
    _proj_env.create(bind, checkfirst=True)
    _mem_role.create(bind, checkfirst=True)
    _prov_type.create(bind, checkfirst=True)

    # ── organizations ─────────────────────────────────────────────────────────
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("website", sa.String(2048), nullable=True),
        sa.Column("logo_url", sa.String(2048), nullable=True),
        sa.Column("billing_email", sa.String(320), nullable=True),
        sa.Column(
            "status",
            _org_status,
            nullable=False,
            server_default="active",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"])
    op.create_index("ix_organizations_status", "organizations", ["status"])
    op.create_index("ix_organizations_cursor", "organizations", ["created_at", "id"])
    op.create_index("ix_organizations_deleted", "organizations", ["deleted_at"])

    # ── projects ──────────────────────────────────────────────────────────────
    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "environment",
            _proj_env,
            nullable=False,
            server_default="production",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_projects_organization_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_projects_org_id", "projects", ["organization_id"])
    op.create_index("ix_projects_environment", "projects", ["environment"])
    op.create_index("ix_projects_org_env", "projects", ["organization_id", "environment"])
    op.create_index("ix_projects_cursor", "projects", ["created_at", "id"])
    op.create_index("ix_projects_deleted", "projects", ["deleted_at"])

    # ── memberships ───────────────────────────────────────────────────────────
    op.create_table(
        "memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_email", sa.String(320), nullable=False),
        sa.Column(
            "role",
            _mem_role,
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_memberships_organization_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("organization_id", "user_email", name="uq_memberships_org_email"),
    )
    op.create_index("ix_memberships_org_id", "memberships", ["organization_id"])
    op.create_index("ix_memberships_email", "memberships", ["user_email"])
    op.create_index("ix_memberships_role", "memberships", ["role"])
    op.create_index("ix_memberships_cursor", "memberships", ["created_at", "id"])
    op.create_index("ix_memberships_deleted", "memberships", ["deleted_at"])

    # ── provider_connections ──────────────────────────────────────────────────
    op.create_table(
        "provider_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider_name", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column(
            "provider_type",
            _prov_type,
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "configuration",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_provider_connections_organization_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_provider_connections_project_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_provider_connections_org_id", "provider_connections", ["organization_id"])
    op.create_index("ix_provider_connections_project_id", "provider_connections", ["project_id"])
    op.create_index("ix_provider_connections_type", "provider_connections", ["provider_type"])
    op.create_index(
        "ix_provider_connections_org_active",
        "provider_connections",
        ["organization_id", "is_active"],
    )
    op.create_index("ix_provider_connections_cursor", "provider_connections", ["created_at", "id"])
    op.create_index("ix_provider_connections_deleted", "provider_connections", ["deleted_at"])


def downgrade() -> None:
    # Drop tables in reverse dependency order
    op.drop_table("provider_connections")
    op.drop_table("memberships")
    op.drop_table("projects")
    op.drop_table("organizations")

    # Drop enum types
    bind = op.get_bind()
    _prov_type.drop(bind, checkfirst=True)
    _mem_role.drop(bind, checkfirst=True)
    _proj_env.drop(bind, checkfirst=True)
    _org_status.drop(bind, checkfirst=True)
