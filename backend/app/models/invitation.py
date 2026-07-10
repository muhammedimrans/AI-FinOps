"""
Invitation ORM model — organization team invitations (EP-24.6).

A separate entity from ``Membership`` (§7's existing invite-by-email
shortcut, ``app/api/v1/organizations.py``'s ``POST /members``): that path
creates a membership immediately, with no consent step and no email sent.
An ``Invitation`` is the real, GitHub/Linear-style flow — nothing is
granted until the invitee actively accepts a token they received by email.
Accepting an invitation creates a ``Membership`` row via the existing
``MembershipRepository``, exactly as ``POST /members`` already does; this
model only tracks the invite-and-accept lifecycle leading up to that.

Only the SHA-256 hash of the raw token is ever stored (mirrors
``VerificationToken``/``PasswordResetToken`` exactly, via the same
``app.auth.tokens.generate_refresh_token()``/``hash_token()`` primitives) —
the raw token exists only in memory for the request that issues it, and in
the URL of the invitation email.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.mixins import BaseModel
from app.models.membership import MembershipRole

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.user import User


class InvitationStatus(enum.StrEnum):
    """Persisted lifecycle states. ``EXPIRED`` is never written by this
    codebase — it is derived at read time from ``PENDING`` + a past
    ``expires_at`` (mirrors how ``VerificationToken``/``PasswordResetToken``
    treat expiry: a filter condition, not a state transition a background
    job has to perform). Kept as an enum member anyway because the schema
    and frontend both need to *report* it as a distinct status."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class Invitation(BaseModel):
    """
    A pending (or resolved) invitation for an email address to join an
    Organization at a given role.

    External ID prefix: ``inv_``  — e.g. ``inv_01j9abc123…``
    """

    __tablename__ = "invitations"
    _external_id_prefix = "inv"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "organizations.id",
            ondelete="CASCADE",
            name="fk_invitations_organization_id",
        ),
        nullable=False,
        index=False,
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[MembershipRole] = mapped_column(
        SQLEnum(
            MembershipRole,
            name="membership_role",
            create_type=False,  # reuses the type Membership.role already created
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=MembershipRole.MEMBER,
    )

    # SHA-256 hex digest only — see module docstring. Re-issued (overwritten)
    # in place on resend, so at most one raw token is ever valid per row.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    status: Mapped[InvitationStatus] = mapped_column(
        SQLEnum(
            InvitationStatus,
            name="invitation_status",
            create_type=True,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=InvitationStatus.PENDING,
    )

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL", name="fk_invitations_created_by"),
        nullable=True,
        default=None,
        index=False,
    )
    accepted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL", name="fk_invitations_accepted_by_user_id"),
        nullable=True,
        default=None,
        index=False,
    )

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    # lazy="raise": accessing without prior selectinload()/joinedload() raises.

    organization: Mapped[Organization] = relationship("Organization", lazy="raise")
    creator: Mapped[User | None] = relationship("User", lazy="raise", foreign_keys=[created_by])
    accepted_by: Mapped[User | None] = relationship(
        "User", lazy="raise", foreign_keys=[accepted_by_user_id]
    )

    __table_args__ = (
        Index("ix_invitations_organization_id", "organization_id"),
        Index("ix_invitations_email", "email"),
        Index("ix_invitations_status", "status"),
        Index("ix_invitations_expires_at", "expires_at"),
        Index("ix_invitations_token_hash", "token_hash"),
    )
