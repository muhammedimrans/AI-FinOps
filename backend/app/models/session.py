"""
Session ORM model — refresh-token bearer record (EP-05 / F-020).

One Session row is created per login. The raw refresh token is never stored;
only the SHA-256 hex digest is persisted. Access tokens are stateless JWTs
and have no corresponding row here.

Lifecycle: active → revoked (via revoked_at) or expired (via expires_at).
Soft-delete (deleted_at) is available for admin hard-removal.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.mixins import BaseModel

if TYPE_CHECKING:
    from app.models.user import User


class Session(BaseModel):
    """
    Refresh-token session bound to a User.

    External ID prefix: ``ses_``  — e.g. ``ses_01j9abc123…``
    """

    __tablename__ = "sessions"
    _external_id_prefix = "ses"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE", name="fk_sessions_user_id"),
        nullable=False,
        index=False,
    )
    refresh_token_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    ip_address: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,
        default=None,
    )
    user_agent: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None,
    )

    user: Mapped[User] = relationship(
        "User",
        lazy="raise",
        foreign_keys=[user_id],
    )

    __table_args__ = (
        Index("ix_sessions_user_id", "user_id"),
        Index("ix_sessions_refresh_token_hash", "refresh_token_hash"),
        Index("ix_sessions_expires_at", "expires_at"),
    )

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None
