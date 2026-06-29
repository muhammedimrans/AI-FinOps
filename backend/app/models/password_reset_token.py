"""
PasswordResetToken ORM model — password reset (EP-05 / F-018).

The raw token is sent to the user's email address; only the SHA-256 hex
digest is stored. Consumed exactly once. All existing reset tokens for a
user are invalidated when a new one is created (used_at set to now).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.mixins import BaseModel

if TYPE_CHECKING:
    from app.models.user import User


class PasswordResetToken(BaseModel):
    """
    Single-use password reset token.

    External ID prefix: ``pr_``  — e.g. ``pr_01j9abc123…``
    """

    __tablename__ = "password_reset_tokens"
    _external_id_prefix = "pr"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE", name="fk_password_reset_tokens_user_id"),
        nullable=False,
        index=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    user: Mapped[User] = relationship(
        "User",
        lazy="raise",
        foreign_keys=[user_id],
    )

    __table_args__ = (
        Index("ix_password_reset_tokens_user_id", "user_id"),
        Index("ix_password_reset_tokens_hash", "token_hash"),
    )
