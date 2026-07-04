"""ModelPricing ORM model — F-051 (EP-09).

Versioned pricing configuration per (provider, model). Supports historical
pricing resolution: multiple versions can exist for the same provider/model,
differentiated by effective_from/effective_to date ranges.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.mixins import BaseModel


class ModelPricing(BaseModel):
    """Versioned pricing record for a (provider, model) pair.

    External ID prefix: ``mpr``
    """

    __tablename__ = "model_pricing"
    _external_id_prefix = "mpr"

    # ── Provider + model identity ─────────────────────────────────────────────

    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="Pricing version identifier, e.g. 'v1' or '2024-01-01'",
    )

    # ── Currency ──────────────────────────────────────────────────────────────

    currency: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        default="USD",
        server_default=text("'USD'"),
    )

    # ── Effective date range ──────────────────────────────────────────────────

    effective_from: Mapped[date] = mapped_column(
        Date(),
        nullable=False,
        comment="Date from which this pricing version is active (inclusive)",
    )
    effective_to: Mapped[date | None] = mapped_column(
        Date(),
        nullable=True,
        default=None,
        comment="Date after which this version is superseded; NULL = currently active",
    )

    # ── Price-per-token fields (Numeric 20,10 for high precision) ─────────────

    prompt_token_price: Mapped[Decimal] = mapped_column(
        Numeric(precision=20, scale=10),
        nullable=False,
        comment="Price per 1 prompt token in the configured currency",
    )
    completion_token_price: Mapped[Decimal] = mapped_column(
        Numeric(precision=20, scale=10),
        nullable=False,
        comment="Price per 1 completion token in the configured currency",
    )
    cached_token_price: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=20, scale=10),
        nullable=True,
        default=None,
        comment="Price per 1 cached token (if supported by provider)",
    )
    audio_token_price: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=20, scale=10),
        nullable=True,
        default=None,
        comment="Price per 1 audio token (if applicable)",
    )
    image_price: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=20, scale=10),
        nullable=True,
        default=None,
        comment="Price per 1 image (if applicable)",
    )
    embedding_price: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=20, scale=10),
        nullable=True,
        default=None,
        comment="Price per 1K tokens for embeddings (if applicable)",
    )

    # ── Status + metadata ─────────────────────────────────────────────────────

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None,
        comment="Optional notes about this pricing version",
    )

    # ── Indexes + constraints ─────────────────────────────────────────────────
    # BaseModel.__init_subclass__ auto-creates:
    #   ix_model_pricing_cursor  (created_at, id)
    #   ix_model_pricing_deleted (deleted_at)

    __table_args__ = (
        UniqueConstraint(
            "provider",
            "model",
            "version",
            name="uq_model_pricing_provider_model_version",
        ),
        Index("ix_model_pricing_provider_model_date", "provider", "model", "effective_from"),
        Index("ix_model_pricing_provider_model_active", "provider", "model", "is_active"),
        Index("ix_model_pricing_effective_range", "effective_from", "effective_to"),
    )
