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
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
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
        SQLEnum(
            UserStatus,
            name="user_status",
            create_type=False,
            values_callable=lambda e: [m.value for m in e],
        ),
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

    # ── Onboarding (EP-21.3) ──────────────────────────────────────────────────
    # NULL = the first-time onboarding wizard (apps/dashboard's /onboarding
    # route) has not been completed yet; set once, on completion, and never
    # cleared. New registrations start NULL; the EP-21.3 migration backfills
    # this to "already completed" for every pre-existing user so onboarding
    # only ever surfaces for genuinely new accounts, not retroactively for
    # people who already know the product.
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    # ── Preferences (EP-22.2) ─────────────────────────────────────────────────
    # Minimal JSON storage for UI preferences (theme, timezone, currency, date
    # format, sidebar-collapsed, notification toggles) — deliberately not a
    # dedicated table (see CLAUDE.md §16). Distinct from
    # app.models.alert.AlertPreference, which is scoped to alert-delivery
    # rules only. Free-form: the frontend owns the key/value shape, the
    # backend only stores and merges it.
    preferences: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )

    # ── Google OAuth (EP-24.5) ────────────────────────────────────────────────
    # Four nullable columns on the existing table rather than a separate
    # oauth_identities entity — Google is the only social provider in scope
    # for this EP (see CLAUDE.md's EP-24.5 section for the full "why not a
    # new table" reasoning); a second provider would be the right trigger to
    # extract a proper polymorphic identities table, not before.
    #
    # google_sub is Google's own stable, unique subject identifier (the "sub"
    # claim of the ID token) — the correct join key, since a Google account's
    # *email* can technically change while sub never does. NULL = no Google
    # account linked. Never store a Google access/refresh token here (Part 9:
    # "never store Google access tokens unless absolutely required") — only
    # the minimal identity fields needed to recognize the account on a future
    # login and display it in Settings.
    google_sub: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    google_email: Mapped[str | None] = mapped_column(String(320), nullable=True, default=None)
    google_linked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    # "password" | "google" — which method most recently authenticated this
    # user; Settings' "Last login provider" display (Part 7). Plain String,
    # not a Postgres ENUM: this is a two-value, display-only field with no
    # DB-level constraint value, and a bare VARCHAR sidesteps the exact
    # postgresql.ENUM double-CREATE-TYPE footgun this codebase's own recent
    # incident review (the EP-24.2 budgets-migration hotfix) documented —
    # not worth the risk for two literal strings.
    last_login_provider: Mapped[str | None] = mapped_column(String(20), nullable=True, default=None)

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
        # Postgres UNIQUE constraints permit multiple NULLs, so users who
        # never linked Google (the common case) never collide with each
        # other on this column.
        UniqueConstraint("google_sub", name="uq_users_google_sub"),
        Index("ix_users_email", "email"),
        Index("ix_users_username", "username"),
        Index("ix_users_status", "status"),
        Index("ix_users_google_sub", "google_sub"),
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
