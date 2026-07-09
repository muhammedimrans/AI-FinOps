"""EP-22.2: user preferences JSON storage

Adds a single ``preferences`` JSONB column to ``users`` — the "minimal
user_preferences JSON storage" the EP-22.2 spec calls for (theme, timezone,
currency, date format, sidebar-collapsed, notification toggles), avoiding a
dedicated ``user_preferences`` table for what is a small, per-user,
schema-flexible bag of UI settings. Not to be confused with
``app.models.alert.AlertPreference`` (EP-19.3), which is scoped specifically
to alert/notification delivery rules, not general UI preferences.

NOT NULL with a server-side default of ``{}`` so existing rows never need a
backfill pass and the column is always JSON-safe to merge into.

Revision ID: d3f6a9c8b2e4
Revises: c7d4f9a1b3e5
Create Date: 2026-07-09 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d3f6a9c8b2e4"
down_revision: str | None = "c7d4f9a1b3e5"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "preferences",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "preferences")
