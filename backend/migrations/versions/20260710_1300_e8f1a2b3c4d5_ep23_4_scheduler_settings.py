"""EP-23.4: organization scheduler settings JSON storage

Adds a single ``sync_settings`` JSONB column to ``organizations`` — the
minimal, schema-flexible bag the background usage-synchronization scheduler
(EP-23.4) needs to read per-organization auto-sync configuration
(``auto_sync_enabled``, ``interval_seconds``), following the exact same
"avoid a dedicated table" pattern EP-22.2 established for
``users.preferences`` (see CLAUDE.md §16 and the migration
``d3f6a9c8b2e4_ep22_2_user_preferences``).

NOT NULL with a server-side default of ``{}`` so existing organizations
never need a backfill pass and are correctly treated as "auto sync
disabled" (missing key, not a stored ``false``) by the scheduler.

Revision ID: e8f1a2b3c4d5
Revises: d3f6a9c8b2e4
Create Date: 2026-07-10 13:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e8f1a2b3c4d5"
down_revision: str | None = "d3f6a9c8b2e4"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column(
            "sync_settings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("organizations", "sync_settings")
