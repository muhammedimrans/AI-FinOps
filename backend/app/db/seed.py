"""
Idempotent demo-data seed.

Shared by two callers:
  - AppContainer.create() at every startup (fast no-op if already seeded)
  - scripts/seed_demo.py for manual one-shot runs

Creates on first startup only:
  Organization  "Zero Protocol"     slug="zero-protocol"   status=ACTIVE
  User          admin@0protocol.net / Admin@123             status=ACTIVE
  Membership    admin@0protocol.net → "Zero Protocol"       role=OWNER
  Project       "AI FinOps Demo"                            environment=PRODUCTION
"""

from __future__ import annotations

import asyncpg
import structlog
from sqlalchemy import and_, select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.password import hash_password
from app.db.mixins import uuid7
from app.models.membership import Membership, MembershipRole
from app.models.organization import Organization, OrganizationStatus
from app.models.project import Project, ProjectEnvironment
from app.models.user import User, UserStatus
from app.repositories.membership_repository import MembershipRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.user_repository import UserRepository

log = structlog.get_logger(__name__)

_SEED_ORG_SLUG = "zero-protocol"
_SEED_ORG_NAME = "Zero Protocol"
_SEED_USER_EMAIL = "admin@0protocol.net"
_SEED_USER_PASSWORD = "Admin@123"  # noqa: S105
_SEED_USER_DISPLAY_NAME = "Admin"
_SEED_PROJECT_NAME = "AI FinOps Demo"


async def seed_demo_data(session: AsyncSession) -> None:
    """
    Idempotent seed. Safe to call on every startup.

    Fast path: returns immediately if admin@0protocol.net already exists,
    making the common (already-seeded) case a single SELECT with no writes.
    When the user is absent every entity is checked and created individually
    so a partially-completed previous run is recovered gracefully.
    """
    user_repo = UserRepository(session)

    # Fast path — nothing to do if the admin user is present.
    if await user_repo.get_by_email(_SEED_USER_EMAIL) is not None:
        log.debug("seed_skipped", reason="admin user already exists")
        return

    log.info("seed_starting")

    # ── Organization ─────────────────────────────────────────────────────────
    org_repo = OrganizationRepository(session)
    org = await org_repo.get_by_slug(_SEED_ORG_SLUG)
    if org is None:
        org = Organization()
        org.id = uuid7()
        org.name = _SEED_ORG_NAME
        org.slug = _SEED_ORG_SLUG
        org.status = OrganizationStatus.ACTIVE
        await org_repo.create(org)
        log.info("seed_created", entity="organization", name=org.name)
    else:
        log.info("seed_exists", entity="organization", name=org.name)

    # ── User ─────────────────────────────────────────────────────────────────
    user = User()
    user.id = uuid7()
    user.email = _SEED_USER_EMAIL
    user.display_name = _SEED_USER_DISPLAY_NAME
    user.username = "admin"
    user.status = UserStatus.ACTIVE
    user.email_verified = True
    user.password_hash = hash_password(_SEED_USER_PASSWORD)
    await user_repo.create(user)
    log.info("seed_created", entity="user", email=user.email)

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
        log.info("seed_created", entity="membership", email=user.email, org=org.name, role="OWNER")

    # ── Project ───────────────────────────────────────────────────────────────
    stmt = select(Project).where(
        and_(
            Project.organization_id == org.id,
            Project.name == _SEED_PROJECT_NAME,
            Project.deleted_at.is_(None),
        )
    )
    result = await session.execute(stmt)
    if result.scalar_one_or_none() is None:
        project = Project()
        project.id = uuid7()
        project.organization_id = org.id
        project.name = _SEED_PROJECT_NAME
        project.environment = ProjectEnvironment.PRODUCTION
        session.add(project)
        await session.flush()
        log.info("seed_created", entity="project", name=project.name)

    await session.commit()
    log.info("seed_complete")


async def seed_startup_data(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """
    Open a session and run seed_demo_data. Called from AppContainer.create().

    If the schema has not been migrated yet (UndefinedTableError / relation does
    not exist), logs a warning and returns so the application can still start.
    All other database errors are re-raised — they indicate a genuine problem
    that should abort startup.

    Production deployment order:
      1. alembic upgrade head   — apply schema migrations
      2. start uvicorn          — this function seeds on first boot
    """
    try:
        async with session_factory() as session:
            await seed_demo_data(session)
    except ProgrammingError as exc:
        if isinstance(exc.__cause__, asyncpg.exceptions.UndefinedTableError):
            log.warning(
                "seed_skipped_database_not_initialized",
                hint="Run 'alembic upgrade head' before starting the application.",
            )
        else:
            raise
