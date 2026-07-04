"""
ProviderConnection ORM model — configured AI provider metadata (§4.5).

Represents a configured connection to an AI provider within an Organization,
optionally scoped to a Project. Stores non-secret metadata only; actual API
credentials are stored by reference in the Secrets store (§4.15 / §4.5).

The ``configuration`` JSONB column holds provider-specific, non-sensitive
metadata (e.g., base URLs, model aliases, rate-limit tiers). Never put API
keys or secrets here.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.mixins import BaseModel

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.project import Project


class ProviderHealthStatus(enum.StrEnum):
    """EP-19.3: connection health, updated by POST /v1/providers/{provider}/test
    (the only place a real health signal exists — see app/alerts/ for how a
    transition fires provider.error/provider.recovery alerts)."""

    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    RECOVERING = "recovering"


class ProviderType(enum.StrEnum):
    """Supported AI provider types — the single catalog of provider slugs
    used both for connected ProviderConnection rows and (EP-16) usage
    ingestion validation. Cohere/Bedrock/Mistral have no adapter yet
    (EP-06/EP-07 territory) but are valid ingestion sources today — a
    caller can report usage for a provider we don't call out to ourselves.
    """

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GROK = "grok"
    GOOGLE = "google"
    AZURE_OPENAI = "azure_openai"
    OPENROUTER = "openrouter"
    OLLAMA = "ollama"
    COHERE = "cohere"
    BEDROCK = "bedrock"
    MISTRAL = "mistral"


class ProviderConnection(BaseModel):
    """
    Configured AI provider connection.

    External ID prefix: ``conn_``  — e.g. ``conn_01j9abc123…``
    project_id is nullable: connections may be org-scoped or project-scoped.
    """

    __tablename__ = "provider_connections"
    _external_id_prefix = "conn"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "organizations.id",
            ondelete="CASCADE",
            name="fk_provider_connections_organization_id",
        ),
        nullable=False,
        index=False,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "projects.id",
            ondelete="SET NULL",
            name="fk_provider_connections_project_id",
        ),
        nullable=True,
        default=None,
        index=False,
    )
    provider_name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_type: Mapped[ProviderType] = mapped_column(
        SQLEnum(
            ProviderType,
            name="provider_type",
            create_type=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    configuration: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    # EP-19.3: health tracking, updated by the provider-test endpoint —
    # nullable/zeroed by default so every pre-existing row degrades to
    # "unknown, never checked" rather than a fabricated "healthy".
    health_status: Mapped[ProviderHealthStatus] = mapped_column(
        SQLEnum(
            ProviderHealthStatus,
            name="provider_health_status",
            create_type=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=ProviderHealthStatus.UNKNOWN,
        server_default=ProviderHealthStatus.UNKNOWN.value,
    )
    last_failure_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    last_recovery_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    consecutive_failure_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    # lazy="raise": accessing without prior selectinload()/joinedload() raises.
    # See docs/engineering/sqlalchemy-loading-strategy.md for the loading policy.

    organization: Mapped[Organization] = relationship(
        "Organization",
        back_populates="provider_connections",
        lazy="raise",
    )
    project: Mapped[Project | None] = relationship(
        "Project",
        back_populates="provider_connections",
        lazy="raise",
    )

    # ── Indexes ───────────────────────────────────────────────────────────────
    # BaseModel.__init_subclass__ appends ix_provider_connections_cursor and
    # ix_provider_connections_deleted automatically.

    __table_args__ = (
        Index("ix_provider_connections_org_id", "organization_id"),
        Index("ix_provider_connections_project_id", "project_id"),
        Index("ix_provider_connections_type", "provider_type"),
        Index("ix_provider_connections_org_active", "organization_id", "is_active"),
    )
