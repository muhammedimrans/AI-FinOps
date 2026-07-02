"""EP-16: extend provider catalog with cohere, bedrock, mistral

The `provider_type` Postgres enum (backing provider_connections.provider_type)
gains three new values so it stays in sync with the Python ProviderType enum,
which EP-16's usage-ingestion validator now reuses as "the existing provider
catalog" (rather than hardcoding a short allowlist). These providers have no
adapter yet (EP-06/EP-07 territory) — only their slug is recognized here.

ADD VALUE is non-blocking and safe inside a transaction on Postgres 12+
(this project targets 16) as long as the new value isn't used in the same
transaction it's added in, which this migration doesn't do.

Downgrade is a no-op: Postgres has no ALTER TYPE ... DROP VALUE, and the
values are additive only — nothing in this migration or after it requires
removing them.

Revision ID: e2b8f387cc86
Revises: f415de1082f8
Create Date: 2026-07-02 16:10:11.752167
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "e2b8f387cc86"
down_revision: str | None = "f415de1082f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_VALUES = ("cohere", "bedrock", "mistral")


def upgrade() -> None:
    for value in _NEW_VALUES:
        op.execute(f"ALTER TYPE provider_type ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE. Reversing this would require
    # rebuilding the enum type from scratch, which risks data loss for any
    # row already using these values — deliberately left as a no-op.
    pass
