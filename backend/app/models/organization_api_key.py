"""
OrganizationApiKey ORM model — organization-scoped API keys (EP-14 Phase 1).

The raw key (``costorah_live_<43 random chars>``) is generated once, shown to
the caller exactly once in the POST response, and never persisted. Only a
SHA-256 hash of the full key is stored (for O(1) lookup on incoming requests
in a later phase) alongside a short, non-secret prefix (for display in the
UI, e.g. ``costorah_live_ab12cd34``) so a key can be recognized without ever
revealing enough of it to reconstruct or brute-force.

Phase 1 scope: issuance, listing, and revocation only. Nothing in this repo
yet authenticates an inbound request with one of these keys — that lands in
a later phase (usage ingestion).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.mixins import BaseModel

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.user import User


class OrganizationApiKey(BaseModel):
    """
    A programmatic API key scoped to one Organization.

    External ID prefix: ``key_``  — e.g. ``key_01j9abc123…``
    """

    __tablename__ = "organization_api_keys"
    _external_id_prefix = "key"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "organizations.id",
            ondelete="CASCADE",
            name="fk_organization_api_keys_organization_id",
        ),
        nullable=False,
        index=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)

    # Non-secret display prefix, e.g. "costorah_live_ab12cd34". Safe to return
    # from GET endpoints and log — never enough characters to reconstruct the key.
    key_prefix: Mapped[str] = mapped_column(String(32), nullable=False)

    # SHA-256 hex digest of the full raw key. The raw key itself is never stored.
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # Permission scopes granted to this key (subset of app.auth.rbac.Permission
    # values). Empty list means no explicit scopes have been granted.
    permissions: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
            name="fk_organization_api_keys_created_by",
        ),
        nullable=True,
        default=None,
        index=False,
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    # lazy="raise": accessing without prior selectinload()/joinedload() raises.

    organization: Mapped[Organization] = relationship(
        "Organization",
        lazy="raise",
    )
    creator: Mapped[User | None] = relationship(
        "User",
        lazy="raise",
        foreign_keys=[created_by],
    )

    __table_args__ = (
        Index("ix_organization_api_keys_organization_id", "organization_id"),
        Index("ix_organization_api_keys_key_hash", "key_hash", unique=True),
        Index("ix_organization_api_keys_created_by", "created_by"),
    )
