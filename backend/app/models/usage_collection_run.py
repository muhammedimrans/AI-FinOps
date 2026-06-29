"""UsageCollectionRun ORM model — F-043 / F-044 (EP-08).

Records every execution of the usage collection pipeline for a provider.
Provides audit trail, status tracking, and error capture.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.mixins import BaseModel


class CollectionRunStatus(enum.StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CollectionTrigger(enum.StrEnum):
    MANUAL = "manual"
    SCHEDULED = "scheduled"


class UsageCollectionRun(BaseModel):
    """One execution of the usage collection pipeline for a provider.

    External ID prefix: ``run_``
    """

    __tablename__ = "usage_collection_runs"
    _external_id_prefix = "run"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "organizations.id",
            ondelete="CASCADE",
            name="fk_usage_collection_runs_organization_id",
        ),
        nullable=False,
    )
    provider_connection_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "provider_connections.id",
            ondelete="SET NULL",
            name="fk_usage_collection_runs_connection_id",
        ),
        nullable=True,
        default=None,
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[CollectionRunStatus] = mapped_column(
        SQLEnum(CollectionRunStatus, name="collection_run_status", create_type=True),
        nullable=False,
        default=CollectionRunStatus.PENDING,
    )
    triggered_by: Mapped[CollectionTrigger] = mapped_column(
        SQLEnum(CollectionTrigger, name="collection_trigger", create_type=True),
        nullable=False,
        default=CollectionTrigger.MANUAL,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    collection_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Start of the date range being collected",
    )
    collection_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="End of the date range being collected",
    )
    events_collected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    events_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pages_fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    collection_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    __table_args__ = (
        Index("ix_usage_collection_runs_org_id", "organization_id"),
        Index("ix_usage_collection_runs_connection_id", "provider_connection_id"),
        Index("ix_usage_collection_runs_provider", "provider"),
        Index("ix_usage_collection_runs_status", "status"),
        Index("ix_usage_collection_runs_org_provider", "organization_id", "provider"),
        Index("ix_usage_collection_runs_started_at", "started_at"),
    )
