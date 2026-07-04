"""
UsageRecord ORM model — the EP-16 usage-ingestion ledger.

One row per successfully ingested `POST /v1/ingest/usage` call. This is a
distinct table from EP-08's UsageEvent / EP-09's UsageCostRecord: those are
built by *our* provider-collection pipeline (we call the provider's API and
compute cost ourselves); UsageRecord is pushed *to* us by an already-billed
caller (SDK, gateway, monitoring agent) who reports their own cost directly
— there is no PricingEngine lookup in this path.

Idempotency
-----------
The unique constraint on (organization_id, request_id) is the entire
duplicate-detection mechanism (F-EP16 "never double count usage"): a second
POST with the same request_id for the same organization is rejected at the
database level even under concurrent requests, not just by an application-
level SELECT-then-INSERT check (which has a race window).
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.mixins import BaseModel


class UsageRecordStatus(enum.StrEnum):
    """Outcome of the underlying AI request, as reported by the caller."""

    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class UsageRecord(BaseModel):
    """
    One ingested usage record.

    External ID prefix: ``usr_``  — e.g. ``usr_01j9abc123…``
    """

    __tablename__ = "usage_records"
    _external_id_prefix = "usr"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "organizations.id",
            ondelete="CASCADE",
            name="fk_usage_records_organization_id",
        ),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "projects.id",
            ondelete="SET NULL",
            name="fk_usage_records_project_id",
        ),
        nullable=True,
        default=None,
    )
    api_key_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "organization_api_keys.id",
            ondelete="SET NULL",
            name="fk_usage_records_api_key_id",
        ),
        nullable=True,
        default=None,
        comment="Which API key ingested this record, for audit/attribution",
    )

    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    request_id: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        comment="Caller-supplied idempotency key, unique per organization",
    )
    status: Mapped[UsageRecordStatus] = mapped_column(
        SQLEnum(
            UsageRecordStatus,
            name="usage_record_status",
            create_type=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=UsageRecordStatus.SUCCESS,
    )

    # ── Token counts ─────────────────────────────────────────────────────────

    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cached_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ── Cost (caller-reported, not computed by our PricingEngine) ──────────────

    cost: Mapped[Decimal] = mapped_column(Numeric(precision=20, scale=8), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")

    # ── Request metadata ────────────────────────────────────────────────────

    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    region: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    usage_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )

    # ── Timing ───────────────────────────────────────────────────────────────

    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When COSTORAH received and stored this record",
    )
    request_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When the underlying AI request occurred, as reported by the caller",
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "request_id", name="uq_usage_records_org_request_id"),
        Index("ix_usage_records_organization_id", "organization_id"),
        Index("ix_usage_records_project_id", "project_id"),
        Index("ix_usage_records_api_key_id", "api_key_id"),
        Index("ix_usage_records_provider", "provider"),
        Index("ix_usage_records_model", "model"),
        Index("ix_usage_records_status", "status"),
        Index("ix_usage_records_request_timestamp", "request_timestamp"),
        Index(
            "ix_usage_records_org_provider_ts",
            "organization_id",
            "provider",
            "request_timestamp",
        ),
        Index(
            "ix_usage_records_org_model_ts",
            "organization_id",
            "model",
            "request_timestamp",
        ),
        Index(
            "ix_usage_records_org_project_ts",
            "organization_id",
            "project_id",
            "request_timestamp",
        ),
    )
