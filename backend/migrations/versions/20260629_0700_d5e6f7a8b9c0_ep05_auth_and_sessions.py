"""EP-05: authentication and session management

Adds the tables and columns required for JWT-based authentication:
  - users.password_hash     : Argon2id hash of the user's password (nullable)
  - sessions                : refresh-token bearer records (F-020)
  - verification_tokens     : single-use email verification tokens (F-019)
  - password_reset_tokens   : single-use password reset tokens (F-018)

All three token tables follow the same pattern:
  - Standard BaseModel columns (id, created_at, updated_at, deleted_at, deleted_by)
  - user_id FK with ON DELETE CASCADE
  - token_hash SHA-256 hex (String 64), expires_at, used_at

Downgrade reverses all changes in strict order.

Revision ID: d5e6f7a8b9c0
Revises: c3d4e5f6a7b8
Create Date: 2026-06-29 07:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d5e6f7a8b9c0"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_UUID = postgresql.UUID(as_uuid=False)


def upgrade() -> None:
    # ── 1. Add password_hash to users ────────────────────────────────────────
    op.add_column(
        "users",
        sa.Column("password_hash", sa.String(256), nullable=True),
    )

    # ── 2. sessions ──────────────────────────────────────────────────────────
    op.create_table(
        "sessions",
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
        sa.Column("user_id", _UUID, nullable=False),
        sa.Column("refresh_token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_sessions_user_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_sessions_cursor", "sessions", ["created_at", "id"])
    op.create_index("ix_sessions_deleted", "sessions", ["deleted_at"])
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_refresh_token_hash", "sessions", ["refresh_token_hash"])
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])

    # ── 3. verification_tokens ────────────────────────────────────────────────
    op.create_table(
        "verification_tokens",
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
        sa.Column("user_id", _UUID, nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_verification_tokens_user_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_verification_tokens_cursor", "verification_tokens", ["created_at", "id"])
    op.create_index("ix_verification_tokens_deleted", "verification_tokens", ["deleted_at"])
    op.create_index("ix_verification_tokens_user_id", "verification_tokens", ["user_id"])
    op.create_index("ix_verification_tokens_hash", "verification_tokens", ["token_hash"])

    # ── 4. password_reset_tokens ──────────────────────────────────────────────
    op.create_table(
        "password_reset_tokens",
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
        sa.Column("user_id", _UUID, nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_password_reset_tokens_user_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_password_reset_tokens_cursor", "password_reset_tokens", ["created_at", "id"]
    )
    op.create_index(
        "ix_password_reset_tokens_deleted", "password_reset_tokens", ["deleted_at"]
    )
    op.create_index(
        "ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"]
    )
    op.create_index(
        "ix_password_reset_tokens_hash", "password_reset_tokens", ["token_hash"]
    )


def downgrade() -> None:
    # ── Reverse 4 ─────────────────────────────────────────────────────────────
    op.drop_index("ix_password_reset_tokens_hash", table_name="password_reset_tokens")
    op.drop_index("ix_password_reset_tokens_user_id", table_name="password_reset_tokens")
    op.drop_index("ix_password_reset_tokens_deleted", table_name="password_reset_tokens")
    op.drop_index("ix_password_reset_tokens_cursor", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")

    # ── Reverse 3 ─────────────────────────────────────────────────────────────
    op.drop_index("ix_verification_tokens_hash", table_name="verification_tokens")
    op.drop_index("ix_verification_tokens_user_id", table_name="verification_tokens")
    op.drop_index("ix_verification_tokens_deleted", table_name="verification_tokens")
    op.drop_index("ix_verification_tokens_cursor", table_name="verification_tokens")
    op.drop_table("verification_tokens")

    # ── Reverse 2 ─────────────────────────────────────────────────────────────
    op.drop_index("ix_sessions_expires_at", table_name="sessions")
    op.drop_index("ix_sessions_refresh_token_hash", table_name="sessions")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_index("ix_sessions_deleted", table_name="sessions")
    op.drop_index("ix_sessions_cursor", table_name="sessions")
    op.drop_table("sessions")

    # ── Reverse 1 ─────────────────────────────────────────────────────────────
    op.drop_column("users", "password_hash")
