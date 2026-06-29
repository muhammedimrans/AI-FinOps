"""
User ORM model — identity anchor for human actors (EP-04, F-013).

A User represents a human who can hold Memberships in one or more
Organizations. Authentication credentials (password hash, OAuth tokens)
are deferred to a later Epic; this entity captures only identity and
profile data.

The ``email`` column carries a unique constraint and is the primary
lookup key. ``display_name`` is a denormalised copy of the user-facing
name shown in the UI.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.mixins import BaseModel

if TYPE_CHECKING:
    from app.models.membership import Membership


class User(BaseModel):
    """
    Human actor in the AI FinOps system.

    External ID prefix: ``usr_``  — e.g. ``usr_01j9abc123…``
    """

    __tablename__ = "users"
    _external_id_prefix = "usr"

    email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    avatar_url: Mapped[str | None] = mapped_column(String(2048), nullable=True, default=None)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)

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
        Index("ix_users_email", "email"),
        Index("ix_users_is_active", "is_active"),
    )
