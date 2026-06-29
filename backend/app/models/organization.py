"""
Organization ORM model — the top-level tenant entity (§4.5, DP-6).

Every other entity in AI FinOps belongs to exactly one Organization.
Soft-delete is the only supported deletion path for normal operations;
hard-delete is an admin-only tool (§4.15 / DP-7).
"""
from __future__ import annotations

import enum
from typing import TYPE_CHECKING

from sqlalchemy import Enum as SQLEnum, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.mixins import BaseModel

if TYPE_CHECKING:
    from app.models.membership import Membership
    from app.models.project import Project
    from app.models.provider_connection import ProviderConnection


class OrganizationStatus(str, enum.Enum):
    """Lifecycle states for an Organization (§4.5)."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"


class Organization(BaseModel):
    """
    Tenant root entity.

    External ID prefix: ``org_``  — e.g. ``org_01j9abc123…``
    Slug must be globally unique (used in URLs and display).
    """

    __tablename__ = "organizations"
    _external_id_prefix = "org"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    website: Mapped[str | None] = mapped_column(String(2048), nullable=True, default=None)
    logo_url: Mapped[str | None] = mapped_column(String(2048), nullable=True, default=None)
    billing_email: Mapped[str | None] = mapped_column(String(320), nullable=True, default=None)
    status: Mapped[OrganizationStatus] = mapped_column(
        SQLEnum(OrganizationStatus, name="organization_status", create_type=True),
        nullable=False,
        default=OrganizationStatus.ACTIVE,
        server_default=OrganizationStatus.ACTIVE.value,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    # String references are resolved lazily by SQLAlchemy after all models load.
    #
    # lazy="raise" — accessing these collections without a prior selectinload()
    # or joinedload() raises InvalidRequestError. This prevents accidental lazy
    # loads that would crash with MissingGreenlet in async context.
    #
    # passive_deletes=True — rely on the DB-level ON DELETE CASCADE constraint
    # rather than loading the collection into Python for orphan detection. This
    # avoids needing to eagerly load children before hard-deleting a parent.
    #
    # Service layer pattern (EP-04+):
    #   from sqlalchemy.orm import selectinload
    #   stmt = select(Organization).options(selectinload(Organization.projects))

    projects: Mapped[list[Project]] = relationship(
        "Project",
        back_populates="organization",
        cascade="all, delete-orphan",
        lazy="raise",
        passive_deletes=True,
    )
    memberships: Mapped[list[Membership]] = relationship(
        "Membership",
        back_populates="organization",
        cascade="all, delete-orphan",
        lazy="raise",
        passive_deletes=True,
    )
    provider_connections: Mapped[list[ProviderConnection]] = relationship(
        "ProviderConnection",
        back_populates="organization",
        cascade="all, delete-orphan",
        lazy="raise",
        passive_deletes=True,
    )

    # ── Constraints / Indexes ─────────────────────────────────────────────────
    # BaseModel.__init_subclass__ appends ix_organizations_cursor and
    # ix_organizations_deleted automatically.

    __table_args__ = (
        UniqueConstraint("slug", name="uq_organizations_slug"),
        Index("ix_organizations_slug", "slug"),
        Index("ix_organizations_status", "status"),
    )
