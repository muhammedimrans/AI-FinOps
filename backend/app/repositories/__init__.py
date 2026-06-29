"""
Repository layer — Ports in the four-layer internal architecture.

Repositories encapsulate all database I/O and expose a clean async interface
to the service layer. They NEVER leak SQLAlchemy ORM objects above this layer.

EP-02: BaseRepository, CursorPage
EP-03: OrganizationRepository, ProjectRepository, MembershipRepository,
       ProviderConnectionRepository
EP-04: UserRepository
EP-08: UsageEventRepository, UsageCollectionRunRepository,
       UsageCollectionCheckpointRepository, ProviderUsageSummaryRepository
"""

from __future__ import annotations

from app.repositories.base_repository import BaseRepository, CursorPage
from app.repositories.membership_repository import MembershipRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.provider_connection_repository import ProviderConnectionRepository
from app.repositories.provider_usage_summary_repository import ProviderUsageSummaryRepository
from app.repositories.usage_collection_checkpoint_repository import (
    UsageCollectionCheckpointRepository,
)
from app.repositories.usage_collection_run_repository import UsageCollectionRunRepository
from app.repositories.usage_event_repository import UsageEventRepository
from app.repositories.user_repository import UserRepository

__all__ = [
    "BaseRepository",
    "CursorPage",
    "MembershipRepository",
    "OrganizationRepository",
    "ProjectRepository",
    "ProviderConnectionRepository",
    "ProviderUsageSummaryRepository",
    "UsageCollectionCheckpointRepository",
    "UsageCollectionRunRepository",
    "UsageEventRepository",
    "UserRepository",
]
