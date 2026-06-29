"""ProviderUsageSummary ORM model — F-041 (EP-08).

Pre-aggregated usage totals per (organization, provider, model, period).
Populated by the collection service after each successful run.  Designed
for fast analytics queries without scanning the full usage_events table.

EP-09 analytics will read from this table.  EP-08 only writes it.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.mixins import BaseModel


class ProviderUsageSummary(BaseModel):
    """Aggregated token and request totals for a (provider, model, period).

    External ID prefix: ``pus_``
    """

    __tablename__ = "provider_usage_summaries"
    _external_id_prefix = "pus"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "organizations.id",
            ondelete="CASCADE",
            name="fk_provider_usage_summaries_organization_id",
        ),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "projects.id",
            ondelete="SET NULL",
            name="fk_provider_usage_summaries_project_id",
        ),
        nullable=True,
        default=None,
    )

    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)

    # Aggregation window — inclusive on both ends
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    total_requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_prompt_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_completion_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_cached_tokens: Mapped[int | None] = mapped_column(BigInteger, nullable=True, default=None)
    total_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "project_id",
            "provider",
            "model",
            "period_start",
            "period_end",
            name="uq_provider_usage_summaries",
        ),
        Index("ix_provider_usage_summaries_org_id", "organization_id"),
        Index("ix_provider_usage_summaries_project_id", "project_id"),
        Index("ix_provider_usage_summaries_provider", "provider"),
        Index("ix_provider_usage_summaries_model", "model"),
        Index("ix_provider_usage_summaries_period", "period_start", "period_end"),
        Index(
            "ix_provider_usage_summaries_org_provider_model",
            "organization_id",
            "provider",
            "model",
        ),
    )
