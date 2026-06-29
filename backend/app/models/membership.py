"""
Membership ORM model — user-to-organization relationship (§5.3.2).

Represents the association between a user (identified by email) and an
Organization, plus the RBAC role they hold within that organization.
No Users table exists yet; email is the identity anchor until EP-04+.

One email address may hold memberships in multiple organizations (each
with a potentially different role), enforced by the unique constraint on
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
    Association between an email address and an Organization.

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
    user_email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[MembershipRole] = mapped_column(
        SQLEnum(MembershipRole, name="membership_role", create_type=True),
        nullable=False,
        default=MembershipRole.MEMBER,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    # lazy="raise": accessing without prior selectinload()/joinedload() raises.
    # See docs/engineering/sqlalchemy-loading-strategy.md for the loading policy.

    organization: Mapped[Organization] = relationship(
        "Organization",
        back_populates="memberships",
        lazy="raise",
    )

    # ── Constraints / Indexes ─────────────────────────────────────────────────
    # BaseModel.__init_subclass__ appends ix_memberships_cursor and
    # ix_memberships_deleted automatically.

    __table_args__ = (
        UniqueConstraint("organization_id", "user_email", name="uq_memberships_org_email"),
        Index("ix_memberships_org_id", "organization_id"),
        Index("ix_memberships_email", "user_email"),
        Index("ix_memberships_role", "role"),
    )
