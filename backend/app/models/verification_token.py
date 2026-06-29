"""
VerificationToken ORM model — email verification (EP-05 / F-019).

The raw token is a cryptographically secure random string sent to the user's
email. Only the SHA-256 hex digest is stored. A token is consumed exactly
once: used_at is set on consumption and subsequent attempts are rejected.
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


class VerificationToken(BaseModel):
    """
    Single-use email verification token.

    External ID prefix: ``vt_``  — e.g. ``vt_01j9abc123…``
    """

    __tablename__ = "verification_tokens"
    _external_id_prefix = "vt"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE", name="fk_verification_tokens_user_id"),
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
        Index("ix_verification_tokens_user_id", "user_id"),
        Index("ix_verification_tokens_hash", "token_hash"),
    )
