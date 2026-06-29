"""UsageCollectionCheckpoint ORM model — F-044 (EP-08).

Tracks the last-successful sync state for each (organization, provider) pair.
Enables incremental collection: the service resumes from the checkpoint rather
than re-fetching the full history on every run.

One checkpoint row per (organization_id, provider, provider_connection_id)
combination.  The unique constraint is enforced at the database level.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.mixins import BaseModel


class UsageCollectionCheckpoint(BaseModel):
    """Incremental sync state for one (org, provider) collection pair.

    External ID prefix: ``chk_``
    """

    __tablename__ = "usage_collection_checkpoints"
    _external_id_prefix = "chk"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "organizations.id",
            ondelete="CASCADE",
            name="fk_usage_checkpoints_organization_id",
        ),
        nullable=False,
    )
    provider_connection_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "provider_connections.id",
            ondelete="SET NULL",
            name="fk_usage_checkpoints_connection_id",
        ),
        nullable=True,
        default=None,
    )
    last_run_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "usage_collection_runs.id",
            ondelete="SET NULL",
            name="fk_usage_checkpoints_last_run_id",
        ),
        nullable=True,
        default=None,
    )

    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    last_collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Upper bound of the last successfully collected date range",
    )
    cursor: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None,
        comment="Opaque page cursor for mid-range resume",
    )
    page_token: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None,
        comment="Provider-specific pagination token",
    )
    sync_state: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        comment="Provider-specific incremental sync metadata",
    )

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "provider",
            "provider_connection_id",
            name="uq_usage_checkpoints_org_provider_connection",
            deferrable=True,
            initially="DEFERRED",
        ),
        Index("ix_usage_checkpoints_org_id", "organization_id"),
        Index("ix_usage_checkpoints_connection_id", "provider_connection_id"),
        Index("ix_usage_checkpoints_provider", "provider"),
        Index("ix_usage_checkpoints_org_provider", "organization_id", "provider"),
    )
