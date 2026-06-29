"""
Project ORM model — attribution unit for cost tracking (§4.5, DP-6).

Projects belong to exactly one Organization and serve as the primary
dimension for cost attribution (every Usage Event resolves to a Project).
"""
from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.mixins import BaseModel

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.provider_connection import ProviderConnection


class ProjectEnvironment(enum.StrEnum):
    """Deployment environment of the Project."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class Project(BaseModel):
    """
    Attribution unit scoped to one Organization.

    External ID prefix: ``proj_``  — e.g. ``proj_01j9abc123…``
    """

    __tablename__ = "projects"
    _external_id_prefix = "proj"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE", name="fk_projects_organization_id"),
        nullable=False,
        index=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    environment: Mapped[ProjectEnvironment] = mapped_column(
        SQLEnum(ProjectEnvironment, name="project_environment", create_type=True),
        nullable=False,
        default=ProjectEnvironment.PRODUCTION,
        server_default=ProjectEnvironment.PRODUCTION.value,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    # lazy="raise": accessing without prior selectinload()/joinedload() raises.
    # See docs/engineering/sqlalchemy-loading-strategy.md for the loading policy.

    organization: Mapped[Organization] = relationship(
        "Organization",
        back_populates="projects",
        lazy="raise",
    )
    provider_connections: Mapped[list[ProviderConnection]] = relationship(
        "ProviderConnection",
        back_populates="project",
        lazy="raise",
    )

    # ── Indexes ───────────────────────────────────────────────────────────────
    # BaseModel.__init_subclass__ appends ix_projects_cursor and
    # ix_projects_deleted automatically.

    __table_args__ = (
        Index("ix_projects_org_id", "organization_id"),
        Index("ix_projects_environment", "environment"),
        Index("ix_projects_org_env", "organization_id", "environment"),
    )
