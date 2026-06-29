# Architecture Changelog

This document records every architectural change made to AI FinOps since the
original Software Design Document (SDD). It is the authoritative record of
decisions that deviate from, refine, or extend the original design.

Entries are append-only. Never delete or modify a prior entry.

---

## Format

```
## [Version] — [Epic] — [Date]
### Change
### Reason
### Impact
### Related Documents
```

---

## [0.1.0] — EP-01 — 2026-06-29

### Change
Repository foundation established. Python 3.13, FastAPI 0.115+, SQLAlchemy 2.x
async, Pydantic v2, structlog, Alembic, asyncpg.

Project layout:
```
backend/
  app/
    api/        — FastAPI routers and dependency injection
    config/     — Pydantic Settings with SecretStr for credentials
    core/       — AppContainer, logging, redis utilities
    db/         — Base, engine, session, mixins, init_db
    middleware/ — RequestLoggingMiddleware
    models/     — ORM models (empty at EP-01)
    repositories/ — Repository layer (empty at EP-01)
  migrations/   — Alembic migration chain
  tests/        — pytest suite
```

### Reason
SDD §3 and §4 specify the four-layer architecture (API → Service → Repository →
Database). EP-01 establishes the project skeleton and tooling baseline before
any domain models exist.

### Impact
All future Epics build on this foundation. No changes to the layering principle
are permitted without an explicit ADR.

### Related Documents
- SDD §3 (System Architecture)
- SDD §4.1 (Technology Stack)
- EP-01 Knowledge Transfer

---

## [0.2.0] — EP-02 — 2026-06-29

### Change
Database infrastructure implemented:
- `BaseModel` mixin combining `UUIDMixin` (UUIDv7 PKs), `TimestampMixin`
  (`created_at`/`updated_at`), and `SoftDeleteMixin` (`deleted_at`/`deleted_by`)
- `BaseRepository[T]` generic with cursor-based pagination keyed on
  `(created_at, id)`
- `AppContainer` managing engine lifecycle; engine pool tuned for Neon
  serverless (pool_pre_ping, pool_recycle=1800)
- `managed_transaction()` using `begin_nested()` for savepoint-based nested
  transactions in background jobs
- Health (`/health`), readiness (`/ready`), and metrics (`/metrics`) endpoints

### Reason
Establishes the database infrastructure required before any domain tables can
be created. UUIDv7 chosen over SERIAL for time-ordering and distributed
generation without coordination. Cursor pagination chosen over offset to avoid
O(n) scan degradation at scale.

### Impact
- All models must inherit from `BaseModel`
- All PKs are UUID v7
- All queries must filter `deleted_at IS NULL` via `_active_query()`
- Offset pagination is prohibited; all list endpoints use cursor tokens

### Related Documents
- SDD §4.2 (UUIDv7), §4.7 (Index Strategy), §API-7 (Pagination)
- EP-02 Knowledge Transfer
- ADR: UUIDv7 primary keys (to be written)

---

## [0.3.0] — EP-03 — 2026-06-29

### Change
Four core domain models introduced:
- `Organization` (tenant root, OrganizationStatus enum: ACTIVE/SUSPENDED/ARCHIVED)
- `Project` (attribution unit, ProjectEnvironment enum: DEVELOPMENT/STAGING/PRODUCTION)
- `Membership` (email → org RBAC, MembershipRole enum: OWNER/ADMIN/MEMBER/VIEWER)
- `ProviderConnection` (AI provider metadata, ProviderType enum: 7 values; JSONB
  `configuration` for non-sensitive metadata only)

Four repositories: `OrganizationRepository`, `ProjectRepository`,
`MembershipRepository`, `ProviderConnectionRepository`.

One Alembic migration (`a3b4c5d6e7f8`): 4 PostgreSQL enum types, 4 tables, 20 indexes.

Bug fixed: `BaseModel.__init_subclass__` was using `getattr()` (MRO-following)
instead of `cls.__dict__.get()` (own-namespace only), causing all concrete models
to skip auto-index creation silently.

### Reason
Load-bearing entities for multi-tenancy, cost attribution, RBAC, and provider
configuration. Cannot build any subsequent Epic without these four tables.

### Impact
- `Organization.id` is the multi-tenancy root; every future table must carry
  `organization_id` FK (DP-6)
- `Project` is the cost attribution unit; every usage event will FK to a Project
- `Membership.user_email` is a temporary identity anchor (no Users table yet);
  must be migrated to `user_id FK` when Users is introduced in EP-04
- `ProviderConnection.configuration` is non-secret metadata only; secrets are
  stored by reference in the Secrets store (EP-05+)
- All relationships declared with `lazy="select"` at this stage (changed in EP-03.5)

### Related Documents
- SDD §4.4 (Conceptual Data Model), §4.5 (Logical Data Model)
- EP-03 Knowledge Transfer
- EP-03 Architecture Review

---

## [0.3.5] — EP-03.5 — 2026-06-29

### Change: H-001 — Application Startup Wiring
`AppContainer.create()` now calls `init_db()` after engine creation. The
application refuses to start if the database is unreachable (fail-fast). `init_db`
was upgraded from stdlib `logging` to `structlog` for structured JSON output.

### Change: H-002 — Provider Configuration Validation
`validate_provider_configuration()` added to `app/core/validators.py`. Rejects
any `configuration` dict containing credential-pattern keys (`api_key`, `secret`,
`password`, `token`, etc.) with a ValueError that lists all violations. Must be
called by the service layer (EP-04+) before persisting ProviderConnection records.

### Change: H-003 — SQLAlchemy Relationship Loading Policy
All relationships across all four EP-03 models changed from `lazy="select"` to
`lazy="raise"`. Accessing an unloaded relationship now raises
`sqlalchemy.exc.InvalidRequestError` instead of silently emitting synchronous SQL
(which crashes with `MissingGreenlet` in async context).

Relationships with `cascade="all, delete-orphan"` (Organization → Projects,
Memberships, ProviderConnections) also set `passive_deletes=True` to rely on
DB-level ON DELETE CASCADE constraints rather than loading children into Python
for orphan detection.

Service layer (EP-04+) must use `selectinload()` or `joinedload()` whenever
relationships are traversed.

### Change: TD-009 — BaseRepository.update() key validation
`update(**kwargs)` now raises `AttributeError` for unknown attribute names,
preventing silent data loss where unknown keys would be set on the Python instance
but never persisted.

### Change: TD-011 — MembershipRepository.list_by_org_and_role() order param
Added `order: str = "asc"` parameter, making the interface consistent with all
other `list_*` methods.

### Change: TD-012 — OrganizationRepository.slug_exists() efficiency
Replaced full-row ORM fetch with `SELECT EXISTS(SELECT 1 ...)`, avoiding
unnecessary column hydration and reducing I/O cost.

### Change: TD-016 — type: ignore explanations
Added inline comments explaining the three `# type: ignore[attr-defined]`
suppressions in `base_repository.py`, preventing future engineers from removing
them incorrectly.

### Change: TD-018 — Shared test factories
Model factory helpers (`make_org`, `make_project`, `make_membership`,
`make_connection`) moved to `tests/conftest.py` as a single canonical source of
truth. All test files import from conftest rather than defining local copies.

### Change: Integration Test Infrastructure
`tests/integration/` package created with database connectivity tests, migration
verification tests, repository CRUD tests, transaction/rollback tests, and
relationship loading tests. All integration tests are marked with
`@pytest.mark.integration` and skipped automatically when `DATABASE_URL` is not
set.

### Change: Documentation
- `docs/engineering/sqlalchemy-loading-strategy.md` — complete guide to loading
  strategy selection for EP-04+ engineers
- `docs/architecture/ARCHITECTURE_CHANGELOG.md` — this file
- `docs/knowledge/EP-03.5-Foundation-Hardening.md` — completion report

### Reason
The EP-03 Architecture Review identified 5 mandatory prerequisites and 15 minor
technical debt items. EP-03.5 addresses all mandatory prerequisites and 6 of the
minor items before EP-04 begins.

### Impact
- **Breaking change for service layer:** All relationship accesses now require
  explicit eager loading. Any EP-04+ code that accesses `org.projects` without
  `selectinload()` will fail with `InvalidRequestError` at runtime.
- **Validator required:** Service layer MUST call `validate_provider_configuration()`
  before persisting ProviderConnection records.
- **Startup reliability:** Application will not start without a live database
  connection, eliminating a class of silent startup failure.
- No schema changes. No new migrations.

### Related Documents
- EP-03 Architecture Review (Section 14 — Production Readiness Checklist)
- docs/engineering/sqlalchemy-loading-strategy.md
- docs/knowledge/EP-03.5-Foundation-Hardening.md

---

*This changelog is maintained by the engineering team. All architectural changes
must be recorded here before the corresponding Epic is marked complete.*
