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
)
from app.db.mixins import (
    SoftDeleteMixin as SoftDeleteMixin,
)
from app.db.mixins import (
    TimestampMixin as TimestampMixin,
)
from app.db.mixins import (
    UUIDMixin as UUIDMixin,
)
from app.db.mixins import (
    uuid7 as uuid7,
)

__all__ = [
    "BaseModel",
    "SoftDeleteMixin",
    "TimestampMixin",
    "UUIDMixin",
    "uuid7",
]
