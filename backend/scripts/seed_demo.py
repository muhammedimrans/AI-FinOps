#!/usr/bin/env python3
"""
Idempotent demo-data seed for the AI FinOps development environment.

Creates (if not already present):
  - Organization  "Zero Protocol"  slug="zero-protocol"  status=ACTIVE
  - User          admin@0protocol.net / Admin@123         status=ACTIVE  email_verified=True
  - Membership    admin@0protocol.net → "Zero Protocol"   role=OWNER
  - Project       "AI FinOps Demo"                        environment=PRODUCTION

Safe to run multiple times — existing rows are left untouched.

Usage:
  cd backend
  python -m scripts.seed_demo
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Allow running as: python -m scripts.seed_demo from backend/
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.password import hash_password
from app.config.settings import get_settings
from app.db.mixins import uuid7
from app.models.membership import Membership, MembershipRole
from app.models.organization import Organization, OrganizationStatus
from app.models.project import Project, ProjectEnvironment
from app.models.user import User, UserStatus
from app.repositories.membership_repository import MembershipRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.user_repository import UserRepository

_SEED_ORG_SLUG = "zero-protocol"
_SEED_ORG_NAME = "Zero Protocol"
_SEED_USER_EMAIL = "admin@0protocol.net"
_SEED_USER_PASSWORD = "Admin@123"
_SEED_USER_DISPLAY_NAME = "Admin"
_SEED_PROJECT_NAME = "AI FinOps Demo"


async def seed(session: AsyncSession) -> None:
    # ── Organization ──────────────────────────────────────────────────────────
    org_repo = OrganizationRepository(session)
    org = await org_repo.get_by_slug(_SEED_ORG_SLUG)
    if org is None:
        org = Organization()
        org.id = uuid7()
        org.name = _SEED_ORG_NAME
        org.slug = _SEED_ORG_SLUG
        org.status = OrganizationStatus.ACTIVE
        await org_repo.create(org)
        print(f"  Created  organization : {org.name} ({org.external_id})")
    else:
        print(f"  Exists   organization : {org.name} ({org.external_id})")

    # ── User ──────────────────────────────────────────────────────────────────
    user_repo = UserRepository(session)
    user = await user_repo.get_by_email(_SEED_USER_EMAIL)
    if user is None:
        user = User()
        user.id = uuid7()
        user.email = _SEED_USER_EMAIL
        user.display_name = _SEED_USER_DISPLAY_NAME
        user.username = "admin"
        user.status = UserStatus.ACTIVE
        user.email_verified = True
        user.password_hash = hash_password(_SEED_USER_PASSWORD)
        await user_repo.create(user)
        print(f"  Created  user         : {user.email} ({user.external_id})")
    else:
        print(f"  Exists   user         : {user.email} ({user.external_id})")

    # ── Membership ────────────────────────────────────────────────────────────
    mem_repo = MembershipRepository(session)
    membership = await mem_repo.get_by_org_and_email(org.id, user.email)
    if membership is None:
        membership = Membership()
        membership.id = uuid7()
        membership.organization_id = org.id
        membership.user_id = user.id
        membership.user_email = user.email
        membership.role = MembershipRole.OWNER
        await mem_repo.create(membership)
        print(f"  Created  membership   : {user.email} → {org.name} (OWNER)")
    else:
        print(f"  Exists   membership   : {user.email} → {org.name} ({membership.role.value})")

    # ── Project ───────────────────────────────────────────────────────────────
    stmt = select(Project).where(
        and_(
            Project.organization_id == org.id,
            Project.name == _SEED_PROJECT_NAME,
            Project.deleted_at.is_(None),
        )
    )
    result = await session.execute(stmt)
    project = result.scalar_one_or_none()

    if project is None:
        project = Project()
        project.id = uuid7()
        project.organization_id = org.id
        project.name = _SEED_PROJECT_NAME
        project.environment = ProjectEnvironment.PRODUCTION
        session.add(project)
        await session.flush()
        await session.refresh(project)
        print(f"  Created  project      : {project.name} ({project.external_id})")
    else:
        print(f"  Exists   project      : {project.name} ({project.external_id})")

    await session.commit()


async def main() -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url), echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    print("Seeding demo data…")
    async with session_factory() as session:
        await seed(session)

    await engine.dispose()
    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
