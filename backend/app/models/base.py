"""
Backward-compatibility shim — do not add new code here.

ORM mixins and BaseModel have moved to app.db.mixins. This module preserves
existing import paths in tests and other modules.

New code should import from app.db directly:
  from app.db.mixins import uuid7, UUIDMixin, TimestampMixin, ...
"""
from __future__ import annotations

from app.db.mixins import (
    BaseModel as BaseModel,
    SoftDeleteMixin as SoftDeleteMixin,
    TimestampMixin as TimestampMixin,
    UUIDMixin as UUIDMixin,
    uuid7 as uuid7,
)

__all__ = [
    "uuid7",
    "UUIDMixin",
    "TimestampMixin",
    "SoftDeleteMixin",
    "BaseModel",
]
