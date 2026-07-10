"""EP-24.5: Google OAuth identity columns on users

Adds four nullable columns to the existing ``users`` table rather than a
new ``oauth_identities`` table — Google is the only social provider in
scope for this EP (see CLAUDE.md's EP-24.5 section for the full "why not a
new table" reasoning). NULL google_sub/google_email/google_linked_at means
"no Google account linked"; NULL last_login_provider means "never logged
in via either method's explicit tracking, or predates this column" (both
treated as unknown, never as a specific provider, by every reader of this
column).

No backfill needed and none performed: every pre-existing user simply
starts with all four columns NULL, which is the correct, honest
"password-only, no recorded last-login-provider" state for accounts that
predate this EP.

Revision ID: a7b8c9d0e1f2
Revises: f1a2b3c4d5e6
Create Date: 2026-07-10 15:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7b8c9d0e1f2"
down_revision: str | None = "f1a2b3c4d5e6"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("google_sub", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("google_email", sa.String(length=320), nullable=True))
    op.add_column(
        "users", sa.Column("google_linked_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("users", sa.Column("last_login_provider", sa.String(length=20), nullable=True))

    op.create_unique_constraint("uq_users_google_sub", "users", ["google_sub"])
    op.create_index("ix_users_google_sub", "users", ["google_sub"])


def downgrade() -> None:
    op.drop_index("ix_users_google_sub", table_name="users")
    op.drop_constraint("uq_users_google_sub", "users", type_="unique")

    op.drop_column("users", "last_login_provider")
    op.drop_column("users", "google_linked_at")
    op.drop_column("users", "google_email")
    op.drop_column("users", "google_sub")
