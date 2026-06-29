"""DailyCostSummary ORM model — F-054 (EP-09).

Pre-aggregated daily cost totals per (organization, project, provider, model).
Built by the AggregationService from UsageCostRecord data. Enables fast
analytics queries without scanning the full cost records table.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import BigInteger, Date, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.mixins import BaseModel


class DailyCostSummary(BaseModel):
    """Pre-aggregated daily cost totals.

    External ID prefix: ``dcs``

    project_id=NULL means the summary covers all projects (org-level rollup).
    """

    __tablename__ = "daily_cost_summaries"
    _external_id_prefix = "dcs"

    # ── Dimension keys ────────────────────────────────────────────────────────

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "organizations.id",
            ondelete="CASCADE",
            name="fk_daily_cost_summaries_organization_id",
        ),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "projects.id",
            ondelete="SET NULL",
            name="fk_daily_cost_summaries_project_id",
        ),
        nullable=True,
        default=None,
        comment="NULL = org-level summary (all projects)",
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    summary_date: Mapped[date] = mapped_column(Date(), nullable=False)

    # ── Aggregated token counts ───────────────────────────────────────────────

    total_prompt_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_completion_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_cached_tokens: Mapped[int | None] = mapped_column(BigInteger, nullable=True, default=None)
    total_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    total_requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ── Aggregated costs (Numeric 20,8) ───────────────────────────────────────

    total_cost: Mapped[Decimal] = mapped_column(Numeric(precision=20, scale=8), nullable=False)
    total_prompt_cost: Mapped[Decimal] = mapped_column(Numeric(precision=20, scale=8), nullable=False)
    total_completion_cost: Mapped[Decimal] = mapped_column(Numeric(precision=20, scale=8), nullable=False)
    total_cached_cost: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=20, scale=8),
        nullable=True,
        default=None,
    )

    # ── Aggregation metadata ──────────────────────────────────────────────────

    event_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of UsageCostRecords aggregated into this summary",
    )

    # ── Indexes + constraints ─────────────────────────────────────────────────
    # BaseModel.__init_subclass__ auto-creates:
    #   ix_daily_cost_summaries_cursor  (created_at, id)
    #   ix_daily_cost_summaries_deleted (deleted_at)

    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "project_id",
            "provider",
            "model",
            "currency",
            "summary_date",
            name="uq_daily_cost_summaries",
        ),
        Index("ix_daily_cost_summaries_org_date", "organization_id", "summary_date"),
        Index("ix_daily_cost_summaries_org_provider_date", "organization_id", "provider", "summary_date"),
        Index("ix_daily_cost_summaries_org_project_date", "organization_id", "project_id", "summary_date"),
        Index("ix_daily_cost_summaries_date", "summary_date"),
    )
