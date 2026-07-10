"""EP-24.6: invitations table for organization team invitations

Adds a single new ``invitations`` table — the real, GitHub/Linear-style
invite-by-email-with-a-token flow. The pre-existing ``POST
/organizations/{id}/members`` immediate-membership shortcut (§7/EP-13) is
left completely unchanged; both coexist (see CLAUDE.md's EP-24.6 section
for why). ``role`` reuses the existing ``membership_role`` Postgres enum
type (``create_type=False`` — it already exists, created by the
``memberships`` table's own migration); ``status`` is a new
``invitation_status`` enum, created and dropped by this migration only.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-07-11 09:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b8c9d0e1f2a3"
down_revision: str | None = "a7b8c9d0e1f2"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # create_type=False for both — membership_role already exists (created
    # by the memberships table's own migration, reused here as-is); the new
    # invitation_status enum is explicitly created below via .create() with
    # checkfirst=True, then referenced with create_type=False so
    # op.create_table() doesn't also try to (re-)issue CREATE TYPE — see
    # EP-24.2's budgets migration for the full explanation of why
    # create_type=True on the table column would double-create and fail.
    membership_role = postgresql.ENUM(
        "owner", "admin", "member", "viewer", name="membership_role", create_type=False
    )
    invitation_status = postgresql.ENUM(
        "pending", "accepted", "expired", "cancelled", name="invitation_status", create_type=False
    )
    bind = op.get_bind()
    invitation_status.create(bind, checkfirst=True)

    op.create_table(
        "invitations",
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
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", membership_role, nullable=False, server_default="member"),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("status", invitation_status, nullable=False, server_default="pending"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("accepted_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_invitations_organization_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="fk_invitations_created_by", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["accepted_by_user_id"],
            ["users.id"],
            name="fk_invitations_accepted_by_user_id",
            ondelete="SET NULL",
        ),
    )

    op.create_index("ix_invitations_cursor", "invitations", ["created_at", "id"])
    op.create_index("ix_invitations_deleted", "invitations", ["deleted_at"])
    op.create_index("ix_invitations_organization_id", "invitations", ["organization_id"])
    op.create_index("ix_invitations_email", "invitations", ["email"])
    op.create_index("ix_invitations_status", "invitations", ["status"])
    op.create_index("ix_invitations_expires_at", "invitations", ["expires_at"])
    op.create_index("ix_invitations_token_hash", "invitations", ["token_hash"])


def downgrade() -> None:
    op.drop_index("ix_invitations_token_hash", table_name="invitations")
    op.drop_index("ix_invitations_expires_at", table_name="invitations")
    op.drop_index("ix_invitations_status", table_name="invitations")
    op.drop_index("ix_invitations_email", table_name="invitations")
    op.drop_index("ix_invitations_organization_id", table_name="invitations")
    op.drop_index("ix_invitations_deleted", table_name="invitations")
    op.drop_index("ix_invitations_cursor", table_name="invitations")
    op.drop_table("invitations")

    bind = op.get_bind()
    postgresql.ENUM(name="invitation_status").drop(bind, checkfirst=True)
