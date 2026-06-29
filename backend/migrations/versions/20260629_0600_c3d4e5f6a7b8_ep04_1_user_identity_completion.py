"""EP-04.1: user identity completion

Closes the gaps identified in the EP-04 verification report:
  - Introduces the ``user_status`` PostgreSQL enum (active / invited / disabled)
  - Replaces the ``is_active`` boolean with ``status`` (data-migrated safely)
  - Adds: username, email_verified, last_login_at, timezone, locale
  - Adds unique constraint uq_users_username and indexes ix_users_username,
    ix_users_status
  - Removes the now-redundant ``is_active`` column and its index

Data migration strategy (zero-downtime expand-contract):
  1. Add ``status`` column as nullable.
  2. Back-fill: is_active=true  → 'active';  is_active=false → 'disabled'.
  3. Make ``status`` NOT NULL.
  4. Drop ``ix_users_is_active`` index then drop ``is_active`` column.

Downgrade reverses all steps in strict order.

Revision ID: c3d4e5f6a7b8
Revises: b1c2d3e4f5a6
Create Date: 2026-06-29 06:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Shared enum definition (create_type=False - managed manually below).
_USER_STATUS = postgresql.ENUM(
    "active", "invited", "disabled", name="user_status", create_type=False
)


def upgrade() -> None:
    # ── 1. Create the user_status PostgreSQL enum type ────────────────────────
    op.execute("CREATE TYPE user_status AS ENUM ('active', 'invited', 'disabled')")

    # ── 2. Add status column as nullable for safe data migration ──────────────
    op.add_column(
        "users",
        sa.Column("status", _USER_STATUS, nullable=True),
    )

    # ── 3. Back-fill status from is_active ────────────────────────────────────
    op.execute("UPDATE users SET status = 'active'   WHERE is_active = true")
    op.execute("UPDATE users SET status = 'disabled' WHERE is_active = false")

    # ── 4. Make status NOT NULL now that every row has a value ────────────────
    op.alter_column("users", "status", nullable=False)

    # ── 5. Drop is_active index then the column itself ────────────────────────
    op.drop_index("ix_users_is_active", table_name="users")
    op.drop_column("users", "is_active")

    # ── 6. Add missing profile / identity columns ─────────────────────────────
    op.add_column(
        "users",
        sa.Column("username", sa.String(50), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "email_verified",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "users",
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("timezone", sa.String(64), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("locale", sa.String(35), nullable=True),
    )

    # ── 7. Constraints and indexes ────────────────────────────────────────────
    op.create_unique_constraint("uq_users_username", "users", ["username"])
    op.create_index("ix_users_username", "users", ["username"])
    op.create_index("ix_users_status", "users", ["status"])


def downgrade() -> None:
    # ── Reverse 7: drop constraints and indexes ───────────────────────────────
    op.drop_index("ix_users_status", table_name="users")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_constraint("uq_users_username", "users", type_="unique")

    # ── Reverse 6: drop added columns ────────────────────────────────────────
    op.drop_column("users", "locale")
    op.drop_column("users", "timezone")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "email_verified")
    op.drop_column("users", "username")

    # ── Restore is_active from status ─────────────────────────────────────────
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean(), nullable=True),
    )
    op.execute(
        "UPDATE users SET is_active = true  WHERE status IN ('active', 'invited')"
    )
    op.execute("UPDATE users SET is_active = false WHERE status = 'disabled'")
    op.alter_column(
        "users",
        "is_active",
        nullable=False,
        server_default=sa.text("true"),
    )
    op.create_index("ix_users_is_active", "users", ["is_active"])

    # ── Drop status column then the enum type ─────────────────────────────────
    op.drop_column("users", "status")
    op.execute("DROP TYPE user_status")
