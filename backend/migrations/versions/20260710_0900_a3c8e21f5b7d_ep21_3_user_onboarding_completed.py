"""EP-21.3: add users.onboarding_completed_at

Backs the first-time onboarding wizard (apps/dashboard's /onboarding
route): NULL means "has not completed onboarding yet", a timestamp means
"completed at this time". No new table — this is a single nullable
timestamp on the existing ``users`` row, following the same minimal,
additive pattern as EP-21.2's ``organizations.is_personal``.

Backfill: unlike is_personal (where "false" is the correct default for
every pre-existing row), the correct default here is the *opposite* of
NULL — pre-existing users already know the product and should not see
onboarding retroactively. So this migration adds the column nullable
with no default, then backfills every existing user's
onboarding_completed_at to the migration's run time in the same
transaction. Only users created *after* this migration runs start out
NULL (i.e. new registrations via ``AuthService.register``, which does
not set this column, matching the "not completed" starting state).

Revision ID: a3c8e21f5b7d
Revises: fe2f617c934d
Create Date: 2026-07-10 09:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3c8e21f5b7d"
down_revision: str | None = "fe2f617c934d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE users SET onboarding_completed_at = now() WHERE onboarding_completed_at IS NULL"
    )


def downgrade() -> None:
    op.drop_column("users", "onboarding_completed_at")
