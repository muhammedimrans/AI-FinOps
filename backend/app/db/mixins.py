"""
Reusable ORM mixins for AI FinOps models.

Provides:
  uuid7()         — time-ordered UUID v7 (no third-party dependency)
  UUIDMixin       — UUID primary key + Stripe-style type-prefixed external ID
  TimestampMixin  — created_at / updated_at with server-side defaults
  SoftDeleteMixin — deleted_at + deleted_by (nullable); NULL means active
  BaseModel       — composite abstract base that all entities inherit from
"""
from __future__ import annotations

import os
import struct
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Index, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# ─── UUIDv7 ──────────────────────────────────────────────────────────────────


def uuid7() -> uuid.UUID:
    """
    Generate a time-ordered UUID v7.

    Layout (128 bits):
      [0:48]   48-bit Unix timestamp in milliseconds
      [48:52]   4-bit version = 0b0111  (7)
      [52:64]  12-bit random seq
      [64:66]   2-bit variant = 0b10
      [66:128] 62-bit random data

    No third-party library required. os.urandom provides
    cryptographic-quality randomness for the random fields.
    """
    timestamp_ms = int(time.time() * 1000) & 0xFFFFFFFFFFFF
    rand_bytes = os.urandom(10)
    rand_a, rand_b = struct.unpack(">HQ", rand_bytes)  # 16-bit + 64-bit

    msb = (timestamp_ms << 16) | (0x7 << 12) | (rand_a & 0x0FFF)
    lsb = (0b10 << 62) | (rand_b & 0x3FFFFFFFFFFFFFFF)
    return uuid.UUID(int=(msb << 64) | lsb)


# ─── Mixins ──────────────────────────────────────────────────────────────────


class UUIDMixin:
    """
    Primary key mixin.

    id          — UUID v7 primary key (time-ordered, §4.19 / ADR-024)
    external_id — type-prefixed hex string for public APIs (e.g. "org_01j…")
                  prefix is defined per-model via _external_id_prefix
    """

    _external_id_prefix: str = "obj"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid7,
        nullable=False,
    )

    @property
    def external_id(self) -> str:
        """Stripe-style type-prefixed public identifier (no hyphens)."""
        return f"{self._external_id_prefix}_{self.id.hex}"


class TimestampMixin:
    """
    Audit timestamp mixin.

    created_at — set once on INSERT via PostgreSQL server default
    updated_at — refreshed on every UPDATE; SQLAlchemy onupdate as fallback
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class SoftDeleteMixin:
    """
    Soft-delete mixin (DP-7).

    deleted_at — NULL means active; non-NULL means logically deleted
    deleted_by — UUID of the actor who deleted the record (nullable)
                 FK constraint to users will be added in a later Epic

    Repositories MUST filter `WHERE deleted_at IS NULL` on normal queries.
    """

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=True,
        default=None,
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def soft_delete(self, deleted_by: uuid.UUID | None = None) -> None:
        """Mark this record as deleted. Caller must flush/commit the session."""
        self.deleted_at = datetime.now(tz=UTC)
        self.deleted_by = deleted_by


# ─── Abstract base model ──────────────────────────────────────────────────────


class BaseModel(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    """
    Abstract base for all AI FinOps ORM entities.

    Concrete models must define __tablename__. Two indexes are auto-created:
      ix_<table>_cursor   — (created_at, id) for efficient cursor pagination
      ix_<table>_deleted  — (deleted_at) for active-record queries
    """

    __abstract__ = True

    @classmethod
    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if not cls.__dict__.get("__abstract__", False):
            table_name = getattr(cls, "__tablename__", cls.__name__.lower())
            existing: tuple[Any, ...] = getattr(cls, "__table_args__", ())
            if isinstance(existing, dict):
                existing = ()
            cls.__table_args__ = (
                *existing,
                Index(f"ix_{table_name}_cursor", "created_at", "id"),
                Index(f"ix_{table_name}_deleted", "deleted_at"),
            )

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} "
            f"id={self.id} external_id={self.external_id}>"
        )
