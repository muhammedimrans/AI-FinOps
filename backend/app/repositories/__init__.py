"""
Repository layer — Ports in the four-layer internal architecture.

Repositories encapsulate all database I/O and expose a clean async interface
to the service layer. They NEVER leak SQLAlchemy ORM objects above this layer.

Add imports here as repositories are implemented in future Epics:
    from app.repositories.organization import OrganizationRepository  # noqa: F401
"""
from __future__ import annotations

from app.repositories.base_repository import BaseRepository, CursorPage

__all__ = ["BaseRepository", "CursorPage"]
