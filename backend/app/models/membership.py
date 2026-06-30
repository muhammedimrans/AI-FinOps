"""
Membership ORM model — user-to-organization relationship (§5.3.2).

Represents the association between a user and an Organization, plus the
RBAC role they hold within that organization.

EP-04 adds ``user_id`` as a nullable FK to the ``users`` table. It is
nullable to preserve backward compatibility with existing rows that were
created when only ``user_email`` was available. New rows created after
EP-04 should always populate both ``user_id`` and ``user_email``.

One user may hold memberships in multiple organizations (each with a
potentially different role), enforced by the unique constraint on
(organization_id, user_email).
"""

from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.mixins import BaseModel

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.user import User


class MembershipRole(enum.StrEnum):
    """
    RBAC roles within an Organization (§5.3.2).

    Billing/Finance and Service Account roles are deferred to a later Epic.
    """

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class Membership(BaseModel):
    """
    Association between a User and an Organization.

    External ID prefix: ``mem_``  — e.g. ``mem_01j9abc123…``
    """

    __tablename__ = "memberships"
    _external_id_prefix = "mem"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "organizations.id",
            ondelete="CASCADE",
            name="fk_memberships_organization_id",
        ),
        nullable=False,
        index=False,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
            name="fk_memberships_user_id",
        ),
        nullable=True,
        default=None,
        index=False,
    )
    user_email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[MembershipRole] = mapped_column(
        SQLEnum(MembershipRole, name="membership_role", create_type=True, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=MembershipRole.MEMBER,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    # lazy="raise": accessing without prior selectinload()/joinedload() raises.

    organization: Mapped[Organization] = relationship(
        "Organization",
        back_populates="memberships",
        lazy="raise",
    )
    user: Mapped[User | None] = relationship(
        "User",
        back_populates="memberships",
        lazy="raise",
    )

    # ── Constraints / Indexes ─────────────────────────────────────────────────
    # BaseModel.__init_subclass__ appends ix_memberships_cursor and
    # ix_memberships_deleted automatically.

    __table_args__ = (
        UniqueConstraint("organization_id", "user_email", name="uq_memberships_org_email"),
        Index("ix_memberships_org_id", "organization_id"),
        Index("ix_memberships_user_id", "user_id"),
        Index("ix_memberships_email", "user_email"),
        Index("ix_memberships_role", "role"),
    )
