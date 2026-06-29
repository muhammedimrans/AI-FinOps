"""
Repository layer — Ports in the four-layer internal architecture.

Repositories encapsulate all database I/O and expose a clean async interface
to the service layer. They NEVER leak SQLAlchemy ORM objects above this layer.

EP-02: BaseRepository, CursorPage
EP-03: OrganizationRepository, ProjectRepository, MembershipRepository,
       ProviderConnectionRepository
"""

from __future__ import annotations

from app.repositories.base_repository import BaseRepository, CursorPage
from app.repositories.membership_repository import MembershipRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.provider_connection_repository import ProviderConnectionRepository

__all__ = [
    "BaseRepository",
    "CursorPage",
    "MembershipRepository",
    "OrganizationRepository",
    "ProjectRepository",
    "ProviderConnectionRepository",
]
