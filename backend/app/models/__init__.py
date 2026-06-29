"""
ORM model package.

Import order matters for Alembic autogenerate and SQLAlchemy mapper
configuration: importing a model here causes SQLAlchemy to register it in
Base.metadata, so env.py only needs to import this package to discover all
tables.

EP-02: base infrastructure (mixins, abstract BaseModel)
EP-03: core domain models (Organization, Project, Membership, ProviderConnection)
"""

import app.db.mixins  # noqa: F401 — registers BaseModel in Base.metadata
from app.models import base  # noqa: F401 — backward-compat re-export

# EP-03 – Core domain models (import order: parent before children)
from app.models.organization import Organization, OrganizationStatus  # noqa: F401
from app.models.project import Project, ProjectEnvironment  # noqa: F401
from app.models.membership import Membership, MembershipRole  # noqa: F401
from app.models.provider_connection import ProviderConnection, ProviderType  # noqa: F401
