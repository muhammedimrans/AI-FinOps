"""EP-25.3: email_delivery_events table for Resend delivery webhooks

Adds a single new ``email_delivery_events`` table — the persisted receiver
for Resend's delivery-status webhooks (Delivered/Bounced/Complained/
Delayed/Sent/Opened/Clicked). No existing table is touched; no email-
sending code path changes. See CLAUDE.md's EP-25.3 section for the full
architecture (app/email/webhook.py, app/api/v1/webhooks.py).

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-07-11 10:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c9d0e1f2a3b4"
down_revision: str | None = "b8c9d0e1f2a3"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "email_delivery_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
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
        sa.Column("provider_message_id", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("recipient_email", sa.String(320), nullable=False),
        sa.Column("subject", sa.String(500), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("raw_payload", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.create_index(
        "ix_email_delivery_events_cursor", "email_delivery_events", ["created_at", "id"]
    )
    op.create_index("ix_email_delivery_events_deleted", "email_delivery_events", ["deleted_at"])
    op.create_index(
        "ix_email_delivery_events_provider_message_id",
        "email_delivery_events",
        ["provider_message_id"],
    )
    op.create_index("ix_email_delivery_events_event_type", "email_delivery_events", ["event_type"])
    op.create_index(
        "ix_email_delivery_events_recipient_email",
        "email_delivery_events",
        ["recipient_email"],
    )


def downgrade() -> None:
    op.drop_table("email_delivery_events")
