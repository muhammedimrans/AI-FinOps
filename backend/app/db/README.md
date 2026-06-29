# app/db — Database Infrastructure

## Purpose

Provides the complete async database infrastructure for AI FinOps. Every
module in this package is reusable foundation code; no business logic lives
here.

## Responsibilities

| Module           | Responsibility                                              |
|------------------|-------------------------------------------------------------|
| `base.py`        | Single SQLAlchemy `DeclarativeBase` — all models inherit it |
| `mixins.py`      | Reusable ORM mixins: UUID PK, timestamps, soft-delete       |
| `engine.py`      | Async engine factory + database health check                |
| `session.py`     | Session factory + `managed_transaction` context manager     |
| `dependencies.py`| FastAPI `get_session` dependency (commit/rollback lifecycle) |
| `init_db.py`     | Startup connectivity verification (never creates tables)    |

## Dependencies

- **SQLAlchemy 2.x async** (`create_async_engine`, `async_sessionmaker`)
- **asyncpg** — PostgreSQL async driver
- **Neon PostgreSQL** — the only database used by this project

## Architecture Decisions

### One DeclarativeBase
`Base` in `base.py` is the single declarative base. All ORM models must
inherit from it (directly or through `BaseModel`) so that
`Base.metadata` contains all table definitions for Alembic autogenerate.

### UUIDv7 Primary Keys
Every entity uses a time-ordered UUID v7 generated client-side (see
`mixins.py:uuid7`). No third-party library is required. Time-ordering
enables efficient cursor-based pagination on `(created_at, id)`.

### Soft Delete
Records are never physically deleted in normal flows. `deleted_at IS NULL`
means active; `deleted_at IS NOT NULL` means logically deleted.
`deleted_by` records which actor performed the deletion (nullable until
the Users table is implemented in a later Epic).

### Session Lifecycle
- `get_session` (FastAPI DI): commits on success, rolls back on exception
- `managed_transaction`: explicit savepoint for nested transactional blocks

### Schema Management
Alembic owns all DDL. `init_db.py` only verifies connectivity.
`Base.metadata.create_all()` is NEVER called in production code.

## Future Implementation

- Add FK constraint `deleted_by → users.id` (EP-03 onwards)
- Add read replica support via secondary engine (future Epic)
- Add query-level instrumentation / OpenTelemetry tracing
