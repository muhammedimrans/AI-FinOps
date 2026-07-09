"""EP-21.2: add organizations.is_personal

Every user now automatically owns exactly one personal workspace,
created at registration (``AuthService.register``) as an
``Organization`` row with ``is_personal=True`` and the registering
user as sole ``OWNER``. This column is the only schema change needed
to distinguish that personal workspace from an ordinary team
organization — no new table, no parallel "workspace" entity.

Additive and backward-compatible: NOT NULL with a ``false`` server
default, so every existing organization row is classified as a normal
(non-personal) org with no backfill required and no risk to existing
data.

Revision ID: fe2f617c934d
Revises: cf91180d80ff
Create Date: 2026-07-09 09:30:38.558217
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "fe2f617c934d"
down_revision: str | None = "cf91180d80ff"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column(
            "is_personal",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("organizations", "is_personal")
