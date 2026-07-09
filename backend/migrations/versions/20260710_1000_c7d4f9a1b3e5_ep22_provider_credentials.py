"""EP-22: secure provider credential storage + validation tracking

Adds four columns to ``provider_connections``:

* ``encrypted_api_key`` — ciphertext only, produced by
  ``app.security.encryption.EncryptionService.encrypt()``. Nullable: a
  connection may exist with no credential yet (freshly created, or a
  provider like Ollama that doesn't require one).
* ``base_url`` — optional override of the provider's default endpoint.
* ``last_validation_status`` — new ``provider_validation_status`` enum,
  the normalized outcome of the most recent credential-validation attempt
  (see ``app.models.provider_connection.ProviderValidationStatus``).
* ``last_error`` — normalized, user-facing error text only (never a raw
  provider response body or the credential value).

All four are nullable/optional additions to an existing table — no backfill
needed, no existing row's behavior changes (a pre-existing connection simply
has no credential configured, exactly as it did before this EP existed).

Revision ID: c7d4f9a1b3e5
Revises: a3c8e21f5b7d
Create Date: 2026-07-10 10:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c7d4f9a1b3e5"
down_revision: str | None = "a3c8e21f5b7d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PROVIDER_VALIDATION_STATUS = postgresql.ENUM(
    "healthy",
    "invalid_api_key",
    "unauthorized",
    "quota_exceeded",
    "network_failure",
    "timeout",
    "provider_unavailable",
    name="provider_validation_status",
    create_type=False,
)


def upgrade() -> None:
    _PROVIDER_VALIDATION_STATUS.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "provider_connections",
        sa.Column("encrypted_api_key", sa.String(length=1024), nullable=True),
    )
    op.add_column(
        "provider_connections",
        sa.Column("base_url", sa.String(length=2048), nullable=True),
    )
    op.add_column(
        "provider_connections",
        sa.Column("last_validation_status", _PROVIDER_VALIDATION_STATUS, nullable=True),
    )
    op.add_column(
        "provider_connections",
        sa.Column("last_error", sa.String(length=1024), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("provider_connections", "last_error")
    op.drop_column("provider_connections", "last_validation_status")
    op.drop_column("provider_connections", "base_url")
    op.drop_column("provider_connections", "encrypted_api_key")
    _PROVIDER_VALIDATION_STATUS.drop(op.get_bind(), checkfirst=True)
