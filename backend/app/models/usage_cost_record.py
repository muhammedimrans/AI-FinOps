"""UsageCostRecord ORM model — F-051 (EP-09).

Computed cost for a single UsageEvent. One cost record per usage event
(enforced by unique constraint). Populated by the PricingEngine after
pricing resolution.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.mixins import BaseModel


class UsageCostRecord(BaseModel):
    """Computed cost record for one UsageEvent.

    External ID prefix: ``ucr``
    """

    __tablename__ = "usage_cost_records"
    _external_id_prefix = "ucr"

    # ── FK references ─────────────────────────────────────────────────────────

    usage_event_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "usage_events.id",
            ondelete="CASCADE",
            name="fk_usage_cost_records_usage_event_id",
        ),
        nullable=False,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "organizations.id",
            ondelete="CASCADE",
            name="fk_usage_cost_records_organization_id",
        ),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "projects.id",
            ondelete="SET NULL",
            name="fk_usage_cost_records_project_id",
        ),
        nullable=True,
        default=None,
    )
    provider_connection_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "provider_connections.id",
            ondelete="SET NULL",
            name="fk_usage_cost_records_connection_id",
        ),
        nullable=True,
        default=None,
    )
    model_pricing_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "model_pricing.id",
            ondelete="SET NULL",
            name="fk_usage_cost_records_model_pricing_id",
        ),
        nullable=True,
        default=None,
    )

    # ── Denormalized provider/model info ──────────────────────────────────────

    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    usage_date: Mapped[date] = mapped_column(
        Date(),
        nullable=False,
        comment="Date portion of the event timestamp for aggregation",
    )

    # ── Token counts ──────────────────────────────────────────────────────────

    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cached_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ── Computed costs (Numeric 20,8 for computed monetary values) ────────────

    prompt_cost: Mapped[Decimal] = mapped_column(
        Numeric(precision=20, scale=8),
        nullable=False,
    )
    completion_cost: Mapped[Decimal] = mapped_column(
        Numeric(precision=20, scale=8),
        nullable=False,
    )
    cached_cost: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=20, scale=8),
        nullable=True,
        default=None,
    )
    total_cost: Mapped[Decimal] = mapped_column(
        Numeric(precision=20, scale=8),
        nullable=False,
    )

    # ── Calculation metadata ──────────────────────────────────────────────────

    calculation_version: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="1.0",
        comment="Version of the pricing calculation algorithm",
    )

    # ── Indexes + constraints ─────────────────────────────────────────────────
    # BaseModel.__init_subclass__ auto-creates:
    #   ix_usage_cost_records_cursor  (created_at, id)
    #   ix_usage_cost_records_deleted (deleted_at)

    __table_args__ = (
        UniqueConstraint(
            "usage_event_id",
            name="uq_usage_cost_records_event",
        ),
        Index("ix_usage_cost_records_org_date", "organization_id", "usage_date"),
        Index("ix_usage_cost_records_org_provider_date", "organization_id", "provider", "usage_date"),
        Index("ix_usage_cost_records_org_project_date", "organization_id", "project_id", "usage_date"),
        Index("ix_usage_cost_records_org_model_date", "organization_id", "model", "usage_date"),
        Index("ix_usage_cost_records_pricing_id", "model_pricing_id"),
    )
