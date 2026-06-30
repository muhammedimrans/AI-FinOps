"""
User ORM model — identity anchor for human actors (EP-04 / EP-04.1).

A User represents a human who can hold Memberships in one or more
Organizations. Authentication credentials (password hash, OAuth tokens)
are deferred to EP-05; this entity captures identity, profile, and
lifecycle state.

Status lifecycle (SDD §4.4):  invited → active → disabled

Backward compatibility:
  The ``is_active`` property (getter + setter) is retained so that any
  existing code written against the EP-04 boolean column continues to
  work without modification.  New code should use ``status`` directly.
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.mixins import BaseModel

if TYPE_CHECKING:
    from app.models.membership import Membership


class UserStatus(enum.StrEnum):
    """
    Lifecycle states for a User (SDD §4.4: invited → active → disabled).

    ACTIVE   — email verified; full platform access.
    INVITED  — invitation sent; email not yet verified.
    DISABLED — account suspended by an administrator.
    """

    ACTIVE = "active"
    INVITED = "invited"
    DISABLED = "disabled"


class User(BaseModel):
    """
    Human actor in the AI FinOps system.

    External ID prefix: ``usr_``  — e.g. ``usr_01j9abc123…``
    """

    __tablename__ = "users"
    _external_id_prefix = "usr"

    # ── Core identity ─────────────────────────────────────────────────────────
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    username: Mapped[str | None] = mapped_column(String(50), nullable=True, default=None)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[UserStatus] = mapped_column(
        SQLEnum(UserStatus, name="user_status", create_type=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=UserStatus.ACTIVE,
        server_default=UserStatus.ACTIVE.value,
    )
    email_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
    )

    # ── Profile ───────────────────────────────────────────────────────────────
    avatar_url: Mapped[str | None] = mapped_column(String(2048), nullable=True, default=None)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True, default=None)
    locale: Mapped[str | None] = mapped_column(String(35), nullable=True, default=None)

    # ── Authentication ────────────────────────────────────────────────────────
    password_hash: Mapped[str | None] = mapped_column(
        String(256),
        nullable=True,
        default=None,
    )

    # ── Session tracking ──────────────────────────────────────────────────────
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    # lazy="raise" prevents accidental N+1 queries in async context.

    memberships: Mapped[list[Membership]] = relationship(
        "Membership",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="raise",
        passive_deletes=True,
    )

    # ── Constraints / Indexes ─────────────────────────────────────────────────
    # BaseModel.__init_subclass__ appends ix_users_cursor and ix_users_deleted.

    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        UniqueConstraint("username", name="uq_users_username"),
        Index("ix_users_email", "email"),
        Index("ix_users_username", "username"),
        Index("ix_users_status", "status"),
    )

    # ── Backward-compat property ──────────────────────────────────────────────

    @property
    def is_active(self) -> bool:
        """True when status is ACTIVE. Retained for backward compatibility."""
        return self.status == UserStatus.ACTIVE

    @is_active.setter
    def is_active(self, value: bool) -> None:
        """Map boolean to ACTIVE / DISABLED for backward compatibility."""
        self.status = UserStatus.ACTIVE if value else UserStatus.DISABLED
