"""UsageEvent ORM model — F-041 (EP-08).

Normalized, provider-agnostic record of a single AI API usage event.
All usage events are scoped to an Organization (tenant isolation) and
optionally to a Project (cost attribution).

Deduplication
-------------
The partial unique index ``ix_usage_events_dedup`` on
``(organization_id, provider, provider_request_id)`` ensures idempotent
collection: re-inserting the same provider event updates the existing row
rather than creating a duplicate.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.mixins import BaseModel


class UsageEvent(BaseModel):
    """One normalized AI API usage record.

    External ID prefix: ``uev_``
    """

    __tablename__ = "usage_events"
    _external_id_prefix = "uev"

    # ── Tenant + attribution ──────────────────────────────────────────────────

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "organizations.id",
            ondelete="CASCADE",
            name="fk_usage_events_organization_id",
        ),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "projects.id",
            ondelete="SET NULL",
            name="fk_usage_events_project_id",
        ),
        nullable=True,
        default=None,
    )
    provider_connection_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "provider_connections.id",
            ondelete="SET NULL",
            name="fk_usage_events_connection_id",
        ),
        nullable=True,
        default=None,
    )
    collection_run_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "usage_collection_runs.id",
            ondelete="SET NULL",
            name="fk_usage_events_collection_run_id",
        ),
        nullable=True,
        default=None,
    )

    # ── Provider identity ─────────────────────────────────────────────────────

    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_request_id: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        comment="Provider's own request ID or a deterministic dedup hash",
    )
    model: Mapped[str] = mapped_column(String(255), nullable=False)

    # ── Timing ────────────────────────────────────────────────────────────────

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When the request occurred (provider time)",
    )

    # ── Token counts ──────────────────────────────────────────────────────────

    request_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cached_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ── Payload ───────────────────────────────────────────────────────────────

    event_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    raw_provider_payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )

    # ── Indexes + constraints ─────────────────────────────────────────────────
    # BaseModel.__init_subclass__ auto-creates:
    #   ix_usage_events_cursor  (created_at, id)
    #   ix_usage_events_deleted (deleted_at)

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "provider",
            "provider_request_id",
            name="uq_usage_events_dedup",
        ),
        Index("ix_usage_events_org_id", "organization_id"),
        Index("ix_usage_events_project_id", "project_id"),
        Index("ix_usage_events_connection_id", "provider_connection_id"),
        Index("ix_usage_events_run_id", "collection_run_id"),
        Index("ix_usage_events_provider", "provider"),
        Index("ix_usage_events_model", "model"),
        Index("ix_usage_events_timestamp", "timestamp"),
        Index("ix_usage_events_org_provider_ts", "organization_id", "provider", "timestamp"),
        Index("ix_usage_events_org_model", "organization_id", "model"),
    )
