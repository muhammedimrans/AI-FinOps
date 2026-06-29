"""
Backward-compatibility shim — do not add new code here.

Repository implementation has moved to app.repositories.base_repository.
New code should import from there directly.
"""

from __future__ import annotations

from app.repositories.base_repository import (
    BaseRepository as BaseRepository,
)
from app.repositories.base_repository import (
    CursorPage as CursorPage,
)
from app.repositories.base_repository import (
    _decode_cursor as _decode_cursor,
)
from app.repositories.base_repository import (
    _encode_cursor as _encode_cursor,
)

__all__ = ["BaseRepository", "CursorPage", "_decode_cursor", "_encode_cursor"]
