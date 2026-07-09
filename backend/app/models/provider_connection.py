"""
ProviderConnection ORM model — configured AI provider connection (§4.5, EP-22).

Represents a configured connection to an AI provider within an Organization,
optionally scoped to a Project. As of EP-22, ``encrypted_api_key`` holds the
actual credential — but only ever as ciphertext produced by
``app.security.encryption.EncryptionService``; the plaintext value never
reaches this model or this table. See CLAUDE.md §13 for the full encryption
and validation architecture.

The ``configuration`` JSONB column holds provider-specific, non-sensitive
metadata (e.g., model aliases, rate-limit tiers). Never put API keys or
secrets here — ``encrypted_api_key`` is the one place a credential-derived
value is allowed to live, and only in encrypted form.
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


class ProviderValidationStatus(enum.StrEnum):
    """EP-22: normalized result of the most recent credential-validation
    attempt (POST .../provider-connections/{id}/test), set by
    ``ProviderValidator``.

    Deliberately a *finer-grained* sibling of ``ProviderHealthStatus``, not a
    replacement: ``health_status`` remains the coarse signal the EP-19.3
    alert engine keys off; ``last_validation_status`` is the specific,
    user-facing reason behind the most recent healthy/critical transition —
    e.g. distinguishing "the key is wrong" from "the provider is down" when
    both map to ``ProviderHealthStatus.CRITICAL``. See
    ``ProviderValidator.normalize_error`` for the mapping from the
    provider-agnostic exception hierarchy in ``app.providers.errors``.
    """

    HEALTHY = "healthy"
    INVALID_API_KEY = "invalid_api_key"
    UNAUTHORIZED = "unauthorized"
    QUOTA_EXCEEDED = "quota_exceeded"
    NETWORK_FAILURE = "network_failure"
    TIMEOUT = "timeout"
    PROVIDER_UNAVAILABLE = "provider_unavailable"


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
    # EP-22: ciphertext only — produced by EncryptionService.encrypt(), in the
    # "v<version>:<token>" format documented on that class. NULL means no
    # credential has been configured yet (e.g. a freshly-created connection,
    # or a provider that doesn't require one, such as Ollama).
    encrypted_api_key: Mapped[str | None] = mapped_column(String(1024), nullable=True, default=None)
    # EP-22: optional override of the provider's default base URL (self-hosted
    # gateways, Azure's per-resource endpoint, etc). SSRF-validated by
    # ProviderConfig at adapter-construction time — see app.providers.config.
    base_url: Mapped[str | None] = mapped_column(String(2048), nullable=True, default=None)
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
    # EP-22: normalized outcome of the most recent validation attempt — see
    # ProviderValidationStatus docstring for how this relates to health_status.
    last_validation_status: Mapped[ProviderValidationStatus | None] = mapped_column(
        SQLEnum(
            ProviderValidationStatus,
            name="provider_validation_status",
            create_type=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=True,
        default=None,
    )
    # EP-22: normalized, user-facing error message only — never the raw
    # provider response body (which can include account/billing details) and
    # never the credential value. Set by ProviderValidator.normalize_error.
    last_error: Mapped[str | None] = mapped_column(String(1024), nullable=True, default=None)

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
