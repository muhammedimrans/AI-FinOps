# EP-02 Code Review & Knowledge Transfer

**Role**: Principal Backend Engineer, Software Architect, and Technical Mentor  
**Audience**: Founder and Product Engineer  
**Project**: AI FinOps — AI Cost Observability Platform  
**Epic**: EP-02 — Database Infrastructure  
**Status**: Complete

---

## Table of Contents

1. [Architectural Review](#1-architectural-review)
2. [Every New Folder Explained](#2-every-new-folder-explained)
3. [Every Important File Explained](#3-every-important-file-explained)
4. [Teaching SQLAlchemy From First Principles](#4-teaching-sqlalchemy-from-first-principles)
5. [Teaching Alembic From First Principles](#5-teaching-alembic-from-first-principles)
6. [Every Mixin Explained](#6-every-mixin-explained)
7. [The Repository Pattern](#7-the-repository-pattern)
8. [Production Code Review](#8-production-code-review)
9. [How EP-03 Builds on EP-02](#9-how-ep-03-builds-on-ep-02)
10. [Architecture Diagrams](#10-architecture-diagrams)
11. [Teaching Summary & Top 10 Concepts](#11-teaching-summary--top-10-concepts)

---

## 1. Architectural Review

### What Was Built

EP-02 created the **database foundation** that every future business entity in AI FinOps will stand on. Think of it as pouring the concrete slab before building a house. No rooms exist yet — but the slab is perfectly engineered.

Four features were delivered:

| Feature | What it is | Analogy |
|---------|-----------|---------|
| F-005 | SQLAlchemy Infrastructure | The plumbing system |
| F-006 | Base ORM Classes | The standard blueprint every room follows |
| F-007 | Alembic Configuration | The building permit and change log |
| F-008 | Repository Layer | The delivery interface between kitchen and dining room |

### Why It Was Built This Way

The central principle is **separation of concerns**. Every file does exactly one thing and has exactly one reason to change. This comes directly from SOLID — specifically the Single Responsibility Principle.

Before EP-02, the project had a single file `core/database.py` doing everything. After EP-02, that same responsibility is split cleanly:

```
Before:              After:
core/database.py  →  db/base.py         (what a model IS)
                     db/engine.py       (how to connect)
                     db/session.py      (how to talk)
                     db/dependencies.py (how FastAPI gets a session)
                     db/init_db.py      (how to start up)
```

The old file is kept as a **shim** (an empty re-export file) so nothing breaks. This is called backward compatibility.

### Inconsistencies Found and Resolved

| Item | Earlier Spec | Revised Spec | Resolution |
|------|-------------|--------------|------------|
| Directory | `app/core/database.py` monolith | `app/db/` split into 6 files | Created `app/db/`; kept `core/database.py` as re-export shim |
| `SoftDeleteMixin` | `deleted_at` only | `deleted_at` + `deleted_by (nullable)` | Added `deleted_by: Mapped[uuid.UUID | None]` and `soft_delete()` method |
| Repository file | `repositories/base.py` | `repositories/base_repository.py` | Created canonical `base_repository.py`; `base.py` is now a shim |
| Initial migration | Not specified | Empty (only Alembic version tracking) | Handwritten empty `upgrade()/downgrade()` |

### Which SDD Sections It Satisfies

- **§3.17.5** — Four-layer architecture: Repositories are the "Ports" layer
- **§4.5 / DP-7** — Soft-delete pattern: `deleted_at IS NULL` means active
- **§4.19 / ADR-024** — UUIDv7 primary keys; type-prefixed external IDs
- **§API-7** — Cursor-based pagination keyed on `(created_at, id)`

### Completed Engineering Execution Pack Items

| EP-02 Item | Status | File |
|-----------|--------|------|
| F-005: Async engine | ✅ | `app/db/engine.py` |
| F-005: Session factory | ✅ | `app/db/session.py` |
| F-005: Session dependency | ✅ | `app/db/dependencies.py` |
| F-005: Transaction helpers | ✅ | `app/db/session.py` |
| F-006: UUIDMixin | ✅ | `app/db/mixins.py` |
| F-006: TimestampMixin | ✅ | `app/db/mixins.py` |
| F-006: SoftDeleteMixin | ✅ | `app/db/mixins.py` |
| F-006: BaseModel | ✅ | `app/db/mixins.py` |
| F-007: Alembic config | ✅ | `migrations/env.py` |
| F-007: Initial migration | ✅ | `migrations/versions/` |
| F-008: BaseRepository | ✅ | `app/repositories/base_repository.py` |
| F-008: Cursor pagination | ✅ | `app/repositories/base_repository.py` |
| Tests: 87/87 passing | ✅ | `backend/tests/` |

---

## 2. Every New Folder Explained

### `backend/app/db/`

**Purpose**: The entire database communication layer lives here. Nothing outside this folder is allowed to know the word "asyncpg" or "connection pool."

**Responsibilities**:
- Define the one-and-only `Base` class all models inherit
- Create and configure the database engine
- Manage session lifecycle
- Provide the FastAPI session dependency
- Define all reusable ORM building blocks (mixins)

**Why it exists**: Before this folder, the database code was scattered. A single file cannot cleanly model six distinct concerns. Separating them means you can read `engine.py` and understand *only* connection pooling — nothing else distracts you.

**How future Epics use it**: In EP-03 and beyond, when someone creates an `Organization` model, they import only one line:
```python
from app.db.mixins import BaseModel
```
That's it. The UUID, timestamps, and soft-delete are all inherited automatically.

---

### `backend/app/repositories/`

**Purpose**: The interface layer between your business logic and the database. Services ask repositories for data; repositories ask SQLAlchemy; SQLAlchemy asks PostgreSQL.

**Responsibilities**:
- CRUD operations on specific entities
- Pagination logic
- Soft-delete filtering
- Transaction management

**Why it exists**: Without repositories, your route handlers would contain raw SQLAlchemy queries. That means when your query logic changes, you change it in 12 different places. Repositories centralize that.

**How future Epics use it**: EP-03 will create `OrganizationRepository(BaseRepository[Organization])`. One line inherits all CRUD for free.

---

### `backend/migrations/`

**Purpose**: The historical record of every schema change, in order, forever.

**Responsibilities**:
- Track which migrations have been applied to which database
- Provide `upgrade()` to apply a change
- Provide `downgrade()` to reverse it

**Why it exists**: You cannot safely change a live database by running `CREATE TABLE` manually. What if two developers do it simultaneously? What if you need to roll back? Alembic solves this by making schema changes code, not manual commands.

**How future Epics use it**: Every time a new entity is added (Organization, User, etc.), a new migration file is generated and committed. The database in production will never be out of sync with the code.

---

### `backend/tests/`

**Purpose**: Automated proof that the code does what you think it does.

**Responsibilities**:
- Unit tests (no database required — run in milliseconds)
- Integration tests (require live Postgres — marked `@pytest.mark.integration`)
- Regression prevention (if someone breaks something, a test fails)

**Why it exists**: Without tests, every code change is a gamble. With tests, you can refactor confidently.

**How future Epics use it**: Each new entity gets its own test file: `test_organization.py`, `test_user.py`, etc. The existing conftest fixtures (`mock_container`, `client`) are reused across all of them.

---

## 3. Every Important File Explained

### `db/engine.py` — The Connection Factory

**What it does**: Creates the async database engine — the object that manages a pool of connections to PostgreSQL.

**Who calls it**: `AppContainer.create()` in `core/container.py` calls `create_engine(settings.database_url)` once at startup. The engine lives for the entire life of the process.

**What problem it solves**: Opening a new database connection for every request is expensive — it takes 50–200ms. Connection pooling (managed by the engine) keeps connections alive and reuses them.

**Pool settings explained**:
```
pool_size=10      → Always keep 10 connections ready
max_overflow=20   → Allow 30 total connections under peak load
pool_timeout=30   → Wait max 30s for a connection before erroring
pool_recycle=1800 → Discard connections older than 30 minutes
pool_pre_ping=True → Test each connection before reuse (Neon kills idle connections)
```

**Why `check_database` doesn't raise**: The health endpoint needs to report degraded status, not crash. If the database is down, the health endpoint should return `{"status": "unhealthy"}` — not a 500 error.

---

### `db/session.py` — The Conversation Manager

**What it does**: Creates `AsyncSession` objects (one per request) and provides `managed_transaction` for explicit transaction control.

**Who calls it**: `AppContainer.create()` calls `create_session_factory(engine)` once. The factory is used by `get_session` on every request.

**`expire_on_commit=False`**: After committing, SQLAlchemy normally "expires" all loaded objects, forcing a database re-read. For async code, that re-read would need to happen inside an async context. Setting this to `False` means loaded objects remain usable after commit — critical for async FastAPI.

**`managed_transaction`**: A context manager that wraps a `SAVEPOINT` in PostgreSQL. Think of it as a sub-transaction:
```
BEGIN
  -- normal request session
  SAVEPOINT
    -- managed_transaction block
  RELEASE SAVEPOINT (or ROLLBACK TO SAVEPOINT on error)
COMMIT
```

---

### `db/dependencies.py` — The FastAPI Bridge

**What it does**: A single async generator function that FastAPI's dependency injection system calls at the start of each request to provide a database session.

**Who calls it**: FastAPI calls `get_session` automatically when a route declares it as a dependency.

**The lifecycle**:
```python
async with session_factory() as session:
    try:
        yield session          # Route runs here
        await session.commit() # All good → commit
    except Exception:
        await session.rollback() # Error → undo everything
        raise
```

**The `yield` keyword**: Everything before `yield` is setup. The value at `yield` is what the route receives. Everything after `yield` is teardown — guaranteed to run even if the route throws an exception.

---

### `db/base.py` — The Single Source of Truth

**What it does**: Defines the one `DeclarativeBase` class that all ORM models inherit from.

**Who calls it**: Every ORM model (directly or through `BaseModel`). Also `migrations/env.py`, which needs `Base.metadata` to know what tables exist.

**What problem it solves**: SQLAlchemy needs a registry to track all models. `Base.metadata` is that registry — a dictionary of all tables. When Alembic runs autogenerate, it compares `Base.metadata` (what your code says the schema should be) against the actual database schema.

**Why it's a separate file**: If `Base` lived in `mixins.py`, importing mixins would always pull in the full model registration machinery. Separation keeps imports clean and prevents circular dependencies.

---

### `db/mixins.py` — The Shared Blueprint

**What it does**: Defines the reusable columns and behaviors that every entity in AI FinOps will have. Also defines `uuid7()` and the composite `BaseModel`.

**Who calls it**: Every future ORM model imports `from app.db.mixins import BaseModel`.

**What problem it solves**: Without mixins, every model would repeat 8–10 columns identically. That's copy-paste code — the most dangerous kind, because when you change the pattern, you must find and update every copy.

---

### `db/init_db.py` — The Startup Handshake

**What it does**: Verifies the database is reachable at application startup and logs the PostgreSQL server version.

**Who calls it**: Will be called by the lifespan context manager in `main.py` during startup. Currently available but not yet wired in (tracked as technical debt).

**Critical rule**: It **never** calls `Base.metadata.create_all()`. Schema is Alembic's job entirely. If `create_all` was called, Alembic would get confused because tables would exist without a recorded migration.

---

### `repositories/base_repository.py` — The Universal Data Interface

**What it does**: Provides all CRUD operations, soft-delete, cursor pagination, and counting for any entity in the system.

**Who calls it**: Future concrete repositories (`OrganizationRepository`, `UserRepository`) inherit from it. Those repositories are then used by service classes.

**The generic type `T`**: `BaseRepository[T]` means "a repository for some model T." When you write `BaseRepository[Organization]`, Python knows that `get()` returns `Organization | None`, `create()` accepts an `Organization`, etc. The type checker enforces this.

---

### `migrations/env.py` — Alembic's Brain

**What it does**: Configures how Alembic connects to the database and discovers your models. Runs every time you execute an Alembic command.

**Two modes**:
- **Offline** (`--sql` flag): generates SQL without connecting — useful for review
- **Online** (default): connects to the real database and applies migrations

**The critical imports**:
```python
from app.db.base import Base
import app.db.mixins   # registers BaseModel in Base.metadata
import app.models      # registers future business models
```

Without these imports, Alembic would see an empty database schema and either generate no migrations or generate migrations that delete everything.

---

## 4. Teaching SQLAlchemy From First Principles

### What Is an ORM?

ORM stands for **Object-Relational Mapper**. It bridges two worlds:
- The **relational world** of databases: rows, columns, tables, SQL
- The **object world** of Python: classes, instances, attributes, methods

**Without an ORM**:
```sql
SELECT id, name, created_at FROM organizations WHERE id = '...'
-- Then manually convert result into a Python dictionary
```

**With SQLAlchemy**:
```python
org = await session.get(Organization, some_uuid)
print(org.name)  # Just Python — no SQL needed
```

SQLAlchemy generates the SQL, executes it, and hands you a Python object. It also tracks changes to that object and knows what SQL to run when you commit.

---

### Why Not Write Raw SQL?

Raw SQL is fine for simple queries. But it breaks down at scale:

| Problem | What goes wrong without ORM |
|---------|---------------------------|
| Type safety | A typo in column name crashes at runtime, not edit time |
| Repetition | Every query re-implements `WHERE deleted_at IS NULL` |
| Migration | You write SQL by hand and hope you got it right |
| Testing | You can't mock SQL easily — you need a real database |
| Refactoring | Rename a column → update SQL in 50 files |
| Security | Manual string interpolation → SQL injection vulnerabilities |

SQLAlchemy solves all of these. It also prevents SQL injection — a critical security concern.

---

### What Is `DeclarativeBase`?

It's the parent class that gives your models their superpowers. When you write:

```python
class Organization(BaseModel):
    __tablename__ = "organizations"
    name: Mapped[str] = mapped_column(String(255))
```

SQLAlchemy intercepts the class creation and:
1. Registers "organizations" as a table in `Base.metadata`
2. Converts `name: Mapped[str]` into a proper column definition
3. Wraps attribute access so `org.name = "Acme"` is tracked as a pending change

Without `DeclarativeBase`, none of that magic happens.

---

### What Is an Engine?

An engine is the **connection pool manager**. It knows the database URL and maintains a pool of open connections. Think of it as a receptionist who manages a team of telephone operators (connections).

```
[Your Code]
     ↓ "I need a connection"
[Engine / Pool]  ← 10 connections pre-warmed
     ↓ hands one back
[PostgreSQL]
```

The engine is created **once** at startup and lives for the whole process lifetime.

---

### What Is a Session?

A session is a **unit of work**. It represents one conversation with the database. Within a session:
- SQLAlchemy tracks which objects you've loaded
- It tracks which objects you've changed (the "identity map")
- It knows what SQL to generate when you commit

Think of it like a shopping cart. You add items, remove items, change items. Nothing is "saved" until checkout (commit). If something goes wrong before checkout, you abandon the cart (rollback).

**One session per request** is the standard pattern. Each HTTP request gets its own session, its own transaction, and its own clean state.

---

### What Is `AsyncSession`?

The same as a Session, but for async Python. Regular SQLAlchemy uses blocking I/O — the Python thread stops and waits for PostgreSQL to respond. `AsyncSession` uses non-blocking I/O — while PostgreSQL is thinking, Python can handle another request.

FastAPI is async. Therefore we must use `AsyncSession`. All `await` keywords on database calls come from this requirement.

```python
# Sync (blocks the thread — wrong for FastAPI):
org = session.get(Organization, id)

# Async (yields control while waiting — correct):
org = await session.get(Organization, id)
```

---

### What Happens During `session.commit()`?

Committing is a multi-step process:

```
1. FLUSH:
   SQLAlchemy generates SQL for all pending changes and sends them.
   (INSERTs for new objects, UPDATEs for modified ones)
   PostgreSQL holds these in a transaction buffer.

2. COMMIT:
   SQLAlchemy tells PostgreSQL "make it permanent."
   PostgreSQL writes to its WAL (write-ahead log) and confirms.

3. EXPIRE (unless expire_on_commit=False):
   SQLAlchemy marks all loaded objects as "stale."
   Next access triggers a re-read from the database.
```

If step 2 fails (e.g., network drops), PostgreSQL automatically rolls back — the data is never partially written.

---

### What Happens During Rollback?

```
1. SQLAlchemy sends ROLLBACK to PostgreSQL
2. PostgreSQL discards all changes made since BEGIN
3. The database is exactly as it was before the transaction started
4. SQLAlchemy clears its identity map (loaded objects are discarded)
```

This is how `get_session` works: if your route raises any exception, `await session.rollback()` is called and the database is unchanged.

---

### How Does FastAPI Get a Database Session?

FastAPI has a concept called **Dependency Injection (DI)**. You declare what a function needs, and FastAPI provides it automatically:

```python
@router.get("/organizations")
async def list_orgs(session: AsyncSession = Depends(get_session)):
    # `session` is already here, clean, and ready to use
    ...
```

When FastAPI sees `Depends(get_session)`, it:
1. Calls `get_session()`
2. The generator runs up to `yield session`
3. FastAPI passes `session` into your route
4. After your route finishes, FastAPI resumes the generator after `yield`
5. `commit()` or `rollback()` is called automatically

---

### How Will Future Models Use the Base Class?

```python
from app.db.mixins import BaseModel
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String

class Organization(BaseModel):
    __tablename__ = "organizations"
    _external_id_prefix = "org"   # → external_id = "org_01j..."

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
```

This 5-line class automatically gets:
- UUID v7 primary key (`id`)
- `created_at`, `updated_at` timestamps
- Soft-delete (`deleted_at`, `deleted_by`, `is_deleted`, `soft_delete()`)
- `external_id` property (`"org_01j..."`)
- Two indexes: `ix_organizations_cursor` and `ix_organizations_deleted`
- `__repr__` method

---

## 5. Teaching Alembic From First Principles

### Why Migrations Exist

Imagine you're running AI FinOps in production with 10,000 organizations stored in PostgreSQL. You need to add a `billing_email` column to the organizations table.

**Option A (dangerous)**: SSH into the server, run `ALTER TABLE organizations ADD COLUMN billing_email TEXT`
- What if it fails halfway? Database is in an unknown state.
- What if a colleague does a different change simultaneously?
- How do you reverse it if it breaks something?
- How does staging or another developer's local environment get the same change?

**Option B (Alembic)**: Write a migration file, commit it, deploy.
- Versioned and tracked
- Applied consistently everywhere
- Reversible
- Safe under concurrent deploys

---

### Why We Never Create Tables Manually

The rule is absolute: **Alembic owns all DDL** (Data Definition Language — `CREATE TABLE`, `ALTER TABLE`, etc.).

`Base.metadata.create_all()` exists but we never use it in production because:
1. It has no concept of versions — can't track what's already been applied
2. It ignores existing tables — silently skips them
3. It cannot roll back
4. It bypasses Alembic's version tracking completely

---

### How Alembic Tracks Versions

Alembic creates a table in your database called `alembic_version`:

```
Table: alembic_version
─────────────────────
version_num (TEXT)   ← e.g. "09c89dba8c85"
```

Every time you run `alembic upgrade head`, Alembic:
1. Reads `alembic_version` to see what version the database is at
2. Looks at the migrations folder to find which revisions are newer
3. Runs each `upgrade()` function in order
4. Updates `alembic_version` to the latest revision ID

---

### What `env.py` Does

`env.py` is the configuration file Alembic reads every time you run a command. It does three things:

**1. Loads your settings** to get the database URL:
```python
settings = get_settings()
url = settings.database_url
```

**2. Imports all your models** so `Base.metadata` is populated:
```python
import app.db.mixins   # registers BaseModel
import app.models      # will register Organization, User, etc.
```

**3. Connects to the database** and applies migrations:
```python
async with engine.connect() as connection:
    await connection.run_sync(do_run_migrations)
```

Without the model imports, Alembic would have an empty `Base.metadata` and would generate migrations that delete all your tables.

---

### What Revision Files Are

Each migration is a Python file with:
- A unique revision ID (hex string like `09c89dba8c85`)
- A `down_revision` pointing to the previous migration
- An `upgrade()` function that applies the change
- A `downgrade()` function that reverses it

They form a **linked list**:
```
None ← 09c89dba8c85 ← (future: abc123) ← (future: def456)
```

`upgrade head` walks this list forward. `downgrade -1` walks one step backward.

---

### `upgrade()` and `downgrade()`

```python
def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
    )

def downgrade() -> None:
    op.drop_table("organizations")
```

The upgrade creates; the downgrade destroys. This symmetry is what makes rollbacks possible.

---

### Autogenerate

Instead of writing `upgrade()` by hand, you run:

```bash
make migrate-create MSG="add organizations table"
```

Alembic:
1. Imports all your models via `env.py`
2. Reads `Base.metadata` — the "desired" schema
3. Connects to the database and reads the "actual" schema
4. **Diffs** them
5. Generates the `upgrade()` and `downgrade()` code for you

This is why `env.py` imports are critical. If `Organization` isn't imported, Alembic won't know the table should exist.

---

### Normal Workflow for Future Migrations

```bash
# 1. Create a new model in Python (e.g., Organization)
#    Add it to app/models/__init__.py

# 2. Generate the migration
make migrate-create MSG="add organizations table"

# 3. Review the generated file in migrations/versions/
#    Verify the upgrade() and downgrade() look correct

# 4. Apply it locally (requires live database)
make migrate

# 5. Commit migration file to Git
git add migrations/versions/...
git commit -m "feat: add organizations table"

# 6. In production: deploy → alembic upgrade head runs automatically
```

---

## 6. Every Mixin Explained

### `UUIDMixin` — The Identity System

**Purpose**: Gives every entity a globally unique identity in two forms:
1. **`id`** — a raw UUID v7, used internally and as the database primary key
2. **`external_id`** — a human-readable, type-prefixed string for APIs

**Why UUID v7 instead of auto-increment integers?**

| Problem with integers | UUID v7 solution |
|----------------------|-----------------|
| Reveals record count ("Organization 12345") | 122 bits of randomness — reveals nothing |
| Predictable — attackers can enumerate records | Time-ordered but not guessable |
| Require a centralized counter | Generated client-side, no coordination needed |
| "Organization 1" and "Project 1" are ambiguous | Each UUID is globally unique across all tables |

**Why type-prefixed external IDs?**

Look at Stripe's API: `ch_1234abc` (charge), `cus_5678def` (customer), `pi_9012ghi` (payment intent). The prefix tells you what type of object it is at a glance.

In AI FinOps:
- `org_01j...` → Organization
- `proj_01j...` → Project
- `usr_01j...` → User

This prevents a subtle but critical bug: passing an organization ID where a project ID is expected. The prefix makes the error visible immediately.

---

### `TimestampMixin` — The Audit Trail

**Purpose**: Automatically records when a record was created and last modified, without any manual code in route handlers or services.

**`server_default=func.now()`**: The default is set on the **PostgreSQL side**, not Python side. This means:
- Even raw SQL inserts (not through your API) get a correct timestamp
- The timestamp uses PostgreSQL's clock — consistent even across multiple app servers

**`onupdate=func.now()`**: Every time SQLAlchemy generates an `UPDATE` statement for this model, it automatically adds `updated_at = now()`. You never have to remember to set it.

**Why `DateTime(timezone=True)`?**: All times are stored as UTC with timezone information. This prevents the classic bug where times look correct locally but are wrong for users in different timezones.

---

### `SoftDeleteMixin` — The Safety Net

**Purpose**: Makes "deletion" reversible. Records are never physically removed from the database — they're marked as deleted.

**Why not just `DELETE FROM table WHERE id = ...`?**

| Hard Delete | Soft Delete |
|------------|-------------|
| Data is gone forever | Data is recoverable |
| Foreign keys break | References remain valid |
| Audit trail lost | You know who deleted it and when |
| Can't undo | Support team can restore |
| GDPR: complicated | GDPR: set a flag and anonymize selectively |

**`deleted_at IS NULL` = active**: This is the core contract. All `_active_query()` calls in the repository add this filter automatically. A deleted record becomes invisible to normal queries.

**`deleted_by`**: Records which user triggered the deletion. Currently nullable (no users table yet), but ready. When EP-03 adds Users, a FK constraint will be added in a migration.

**`soft_delete()` method**: Sets both `deleted_at` and `deleted_by` in a single call. You can never set `deleted_at` without recording who did it. The atomicity prevents "half-deleted" state.

---

### `BaseModel` — The Foundation Stone

**Purpose**: Composites all three mixins plus `Base` into a single class that every entity inherits.

```
Base (SQLAlchemy DeclarativeBase)
  + UUIDMixin (id, external_id)
  + TimestampMixin (created_at, updated_at)
  + SoftDeleteMixin (deleted_at, deleted_by, is_deleted, soft_delete)
  = BaseModel
```

**`__abstract__ = True`**: Tells SQLAlchemy "don't create a table for this class." `BaseModel` is a blueprint, not a room.

**`__init_subclass__`**: Python metaclass magic. Every time a class inherits from `BaseModel`, this method runs automatically and adds two indexes to every concrete table:
- `ix_<table>_cursor` on `(created_at, id)` — for cursor pagination
- `ix_<table>_deleted` on `(deleted_at)` — for `WHERE deleted_at IS NULL` queries

**Example — Organization in EP-03**:
```python
class Organization(BaseModel):
    __tablename__ = "organizations"
    _external_id_prefix = "org"

    name: Mapped[str] = mapped_column(String(255))
    # id, created_at, updated_at, deleted_at, deleted_by,
    # is_deleted, external_id, __repr__ → ALL inherited
```

---

## 7. The Repository Pattern

### Why Do We Use `BaseRepository`?

**Without repositories**, a route handler contains raw queries:
```python
@router.get("/organizations/{org_id}")
async def get_org(org_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    stmt = (
        select(Organization)
        .where(Organization.id == org_id)
        .where(Organization.deleted_at.is_(None))
    )
    result = await session.execute(stmt)
    org = result.scalar_one_or_none()
    if org is None:
        raise HTTPException(404)
    return org
```

**With repositories**:
```python
@router.get("/organizations/{org_id}")
async def get_org(org_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    repo = OrganizationRepository(session)
    org = await repo.get_or_raise(org_id)
    return org
```

The second version is shorter, more readable, and — most importantly — the query logic lives once, in one place.

---

### The Specific Advantages

**1. Testability**
Without repositories, you must connect to a real database to test a route. With repositories, you can mock them:
```python
mock_repo = MagicMock()
mock_repo.get.return_value = fake_org
# Now test the route without a database
```

**2. Single place to fix bugs**
If you discover that a query doesn't filter deleted records correctly, you fix `_active_query()` in `BaseRepository` — and every repository in the system is fixed simultaneously.

**3. Soft-delete enforcement**
The repository guarantees that `deleted_at IS NULL` is always applied. No developer can accidentally return deleted records by writing their own query.

**4. Pagination in one place**
Cursor-based pagination is complex. It lives once in `list_page()`. Every entity gets it for free.

**5. Transaction boundary clarity**
Repositories flush; they never commit. The commit happens in `get_session`. This is a strict contract that prevents "double commit" bugs.

---

### Future Repositories in EP-03 and Beyond

```python
# EP-03 — inherits everything, only adds what's unique
class OrganizationRepository(BaseRepository[Organization]):
    model = Organization
    # Inherits: get, get_or_raise, create, update,
    #           soft_delete, hard_delete, list_page, count

    async def get_by_slug(self, slug: str) -> Organization | None:
        # Custom query specific to organizations
        stmt = self._active_query().where(Organization.slug == slug)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
```

You only write what's unique to `Organization`. Everything common is inherited.

---

## 8. Production Code Review

### Good Decisions

**`expire_on_commit=False`**
Essential for async SQLAlchemy. Without this, accessing an attribute after a commit would require a database round-trip inside a context that might no longer have an active session. This is a common source of confusing async errors.

**`pool_pre_ping=True`**
Neon PostgreSQL terminates idle connections. Without pre-ping, the first request after a period of inactivity would fail with a "connection closed" error. This setting silently tests and replaces stale connections.

**Health check returns dict, never raises**
The health endpoint's job is to report status, not propagate errors. If this raised, `/health` would return 500 instead of useful health information.

**`uuid7()` without a third-party library**
No dependency = no supply chain risk, no version conflicts, no license complications. The implementation is correct and well-tested.

**`__init_subclass__` for automatic indexes**
Elegant. Developers who add new models cannot forget to add pagination and soft-delete indexes — the system adds them automatically.

**Backward-compat shims**
`core/database.py` pointing to `app.db.*` means no existing imports break. Clean migration path with no big-bang refactor.

**`get_or_raise` pattern**
Provides a `KeyError` (not a 404) so the service/route layer decides how to handle missing records. The repository doesn't dictate HTTP behavior — correct separation of concerns.

---

### Potential Improvements & Technical Debt

**1. `extra_filters` parameter is too loose**
```python
async def list_page(self, ..., extra_filters: Any = None)
```
`Any` bypasses type checking. Better type: `ColumnElement[bool] | None` from SQLAlchemy. Tracked as future cleanup.

**2. `deleted_by` has no FK constraint yet**
`deleted_by` is a raw UUID with no foreign key to a users table. You could set it to a non-existent UUID and the database would accept it. Intentional (users table doesn't exist yet), but tracked as technical debt.

**3. `init_db.py` is not yet wired into the app lifespan**
`init_db()` exists but isn't called at startup. A misconfigured `DATABASE_URL` won't be discovered until the first request hits. Should be wired in EP-03.

**4. `update()` with `**kwargs` is untyped**
```python
async def update(self, instance: T, **kwargs: Any) -> T:
```
A developer could pass a non-existent field name and get an `AttributeError` at runtime. Typed update using `TypedDict` or Pydantic schemas would catch this at edit time.

**5. No query timeout configuration**
Long-running database queries will block indefinitely. Production systems should set `command_timeout` in asyncpg or use SQLAlchemy's `execution_options(timeout=30)`.

---

### Security Notes

**Cursor tokens are not signed**
The base64 cursor encodes `created_at` and `id`. A malicious client could decode it, modify the timestamp, and re-encode it. For internal APIs this is fine. For public APIs, HMAC-signing the cursor token would prevent tampering.

**`str(exc)` in health check**
Database error messages can include connection strings, usernames, or internal schema details. The health endpoint should be restricted to internal access only (not public-facing), or the error message should be sanitized in production.

---

## 9. How EP-03 Builds on EP-02

### The Exact Inheritance Chain

```
app/db/base.py
└── Base (DeclarativeBase)
    └── app/db/mixins.py
        └── BaseModel (abstract)
            └── app/models/organization.py  [EP-03]
                └── Organization
                    └── app/repositories/organization.py  [EP-03]
                        └── OrganizationRepository
                            └── app/services/organization.py  [EP-03+]
                                └── OrganizationService
                                    └── app/api/v1/organizations.py  [EP-03+]
                                        └── GET /organizations
                                            POST /organizations
                                            GET /organizations/{id}
                                            DELETE /organizations/{id}
```

### Which EP-02 Files EP-03 Will Reuse

| EP-02 File | How EP-03 Uses It |
|-----------|------------------|
| `db/base.py` | `Organization` inherits `Base` through `BaseModel` |
| `db/mixins.py` | `Organization` inherits `BaseModel` |
| `db/engine.py` | No change — same engine |
| `db/session.py` | No change — same sessions |
| `db/dependencies.py` | No change — same DI |
| `repositories/base_repository.py` | `OrganizationRepository` inherits `BaseRepository[Organization]` |
| `migrations/env.py` | Will import `app.models.organization` for autogenerate |

### What EP-03 Will Add

```
app/models/organization.py          ← NEW: Organization ORM model
app/repositories/organization.py    ← NEW: OrganizationRepository
app/models/__init__.py              ← MODIFIED: import organization
migrations/versions/yyyymmdd_*.py   ← NEW: organizations migration
tests/test_organization.py          ← NEW: repository + API tests
```

---

## 10. Architecture Diagrams

### Diagram 1 — Full Request Lifecycle

```
HTTP Request: GET /api/v1/organizations
                    │
                    ▼
         ┌──────────────────────┐
         │   FastAPI Router      │
         │   (api/v1/...)        │
         └──────────┬───────────┘
                    │
                    │  FastAPI DI resolves Depends(get_session)
                    ▼
         ┌──────────────────────┐
         │   get_session()       │
         │   (db/dependencies)   │
         │                       │
         │   BEGIN transaction   │
         └──────────┬───────────┘
                    │  yields AsyncSession
                    ▼
         ┌──────────────────────┐
         │   Route Handler       │
         │                       │
         │   repo = OrgRepo()    │
         └──────────┬───────────┘
                    │
                    ▼
         ┌──────────────────────┐
         │   OrganizationRepo    │
         │   (repositories/)     │
         │                       │
         │   _active_query()     │
         │   WHERE deleted_at    │
         │   IS NULL             │
         └──────────┬───────────┘
                    │  SELECT statement
                    ▼
         ┌──────────────────────┐
         │   AsyncSession        │
         │   (db/session.py)     │
         │                       │
         │   execute(stmt)       │
         └──────────┬───────────┘
                    │  SQL over connection pool
                    ▼
         ┌──────────────────────┐
         │   AsyncEngine         │
         │   (db/engine.py)      │
         │                       │
         │   Pool of 10 conns    │
         └──────────┬───────────┘
                    │  TCP connection
                    ▼
         ┌──────────────────────┐
         │   Neon PostgreSQL     │
         │                       │
         │   SELECT * FROM       │
         │   organizations       │
         │   WHERE deleted_at    │
         │   IS NULL             │
         └──────────┬───────────┘
                    │  Result rows
                    ◄──────────── (travels back up the chain)
                    │
                    ▼
         ┌──────────────────────┐
         │   get_session()       │
         │                       │
         │   COMMIT (success)    │
         │   or ROLLBACK (error) │
         └──────────────────────┘
                    │
                    ▼
         HTTP Response: 200 OK + JSON
```

---

### Diagram 2 — Application Startup Sequence

```
uvicorn starts
     │
     ▼
app/main.py: create_app(settings)
     │
     ▼
lifespan() context manager begins
     │
     ▼
AppContainer.create(settings)
     │
     ├── create_engine(settings.database_url)
     │         └── connection pool ready (lazy — no socket yet)
     │
     ├── create_session_factory(engine)
     │         └── factory function ready
     │
     └── create_redis(settings.redis_url)
               └── Redis pool ready (lazy)
     │
     ▼
app.state.container = container
     │
     ▼
[Application ready — accepting requests]
     │
     ▼
[Shutdown signal received]
     │
     ▼
lifespan() cleanup
     │
     ├── engine.dispose()   ← closes all DB connections gracefully
     └── redis.aclose()     ← closes Redis connections
```

---

### Diagram 3 — Migration Lifecycle

```
Developer adds Organization model to app/models/organization.py
                    │
                    ▼
make migrate-create MSG="add organizations table"
                    │
                    ▼
Alembic runs env.py:
  import app.db.mixins   → BaseModel registered in Base.metadata
  import app.models      → Organization registered in Base.metadata
                    │
                    ▼
Alembic compares:
  Base.metadata (desired) ←→ PostgreSQL schema (actual)
                    │
                    ▼
Generates migrations/versions/20260630_organizations.py:

  def upgrade():
      op.create_table("organizations",
          sa.Column("id", postgresql.UUID(), primary_key=True),
          sa.Column("name", sa.String(255), nullable=False),
          sa.Column("created_at", sa.DateTime(timezone=True)),
          ...
      )
      op.create_index("ix_organizations_cursor", "organizations",
          ["created_at", "id"])

  def downgrade():
      op.drop_index("ix_organizations_cursor")
      op.drop_table("organizations")
                    │
                    ▼
Developer reviews the file, commits to Git
                    │
                    ▼
make migrate  (in production CI/CD)
                    │
                    ▼
Alembic reads alembic_version from PostgreSQL
  (currently: "09c89dba8c85" — the empty initial migration)
                    │
                    ▼
Applies upgrade() for the new revision
  → CREATE TABLE organizations (...)
  → UPDATE alembic_version SET version_num = "new_rev_id"
                    │
                    ▼
Database schema now matches code ✓
```

---

### Diagram 4 — Object Inheritance Chain

```
DeclarativeBase (SQLAlchemy built-in)
└── Base (app/db/base.py)
    │
    └── combined with Python mixins:
        ├── UUIDMixin     → id (UUID v7 PK), external_id property
        ├── TimestampMixin → created_at, updated_at
        └── SoftDeleteMixin → deleted_at, deleted_by,
                              is_deleted property, soft_delete()
        │
        └── BaseModel (app/db/mixins.py)
              __abstract__ = True
              → Auto-creates indexes via __init_subclass__
              → __repr__
              │
              ├── Organization(BaseModel)  [EP-03]
              │     __tablename__ = "organizations"
              │     _external_id_prefix = "org"
              │     name, slug, billing_email, ...
              │
              ├── Project(BaseModel)  [EP-03+]
              │     __tablename__ = "projects"
              │     _external_id_prefix = "proj"
              │     organization_id (FK), name, ...
              │
              ├── ProviderConnection(BaseModel)  [EP-04+]
              │     __tablename__ = "provider_connections"
              │     _external_id_prefix = "prov"
              │     project_id (FK), provider_type, ...
              │
              └── UsageEvent(BaseModel)  [EP-05+]
                    __tablename__ = "usage_events"
                    _external_id_prefix = "evt"
                    provider_connection_id (FK), cost, ...
```

---

## 11. Teaching Summary & Top 10 Concepts

### What Was Built in EP-02

EP-02 created the invisible infrastructure that makes AI FinOps's database layer professional-grade. No business data exists yet. What exists is a perfectly engineered foundation:

- A database connection system that's async, pooled, and health-monitored
- A model system where every entity automatically gets identity, timestamps, and soft-delete
- A migration system that makes every schema change safe, versioned, and reversible
- A repository system that centralizes all database queries and enforces consistency

All 87 tests pass. Coverage is at 71% (above the 70% required threshold).

---

### Top 10 Things to Understand Before Starting EP-03

**1. There is one `Base` (in `app/db/base.py`)**
Every ORM model in the system inherits from this. `Base.metadata` is the single registry of all tables. Alembic reads it. Never create a second `Base`.

**2. `BaseModel` is abstract — it has no table**
It's a blueprint. Only classes that inherit it and set `__tablename__` get real tables in PostgreSQL.

**3. The engine lives once; sessions live per-request**
Engine = startup to shutdown. Session = one HTTP request. Never hold a session open across multiple requests.

**4. Repositories flush; they never commit**
`get_session()` owns the commit. Repositories only flush (send SQL to the database's transaction buffer). This is a strict, non-negotiable boundary.

**5. `deleted_at IS NULL` = the record is active**
Every query in the system uses `_active_query()` which adds this filter. Deleted records are invisible by default. This is the core soft-delete contract.

**6. Never call `Base.metadata.create_all()`**
Alembic owns all DDL. `create_all` bypasses version tracking and is forbidden in production code. Tables are created only through migration files.

**7. Alembic migration files must be committed to Git**
They are code. They are the deployment mechanism for database changes. A missing migration file means production doesn't match the code.

**8. `env.py` must import every model for autogenerate to work**
If `Organization` isn't imported in `env.py` (via `app.models`), Alembic won't know the table should exist and will generate an empty migration.

**9. `external_id` is for APIs, `id` is internal**
Never expose raw database UUIDs in API responses. Use `org.external_id` (`"org_01j..."`) in JSON. The prefix tells the caller — and you — what type of object it is at a glance.

**10. `uuid7()` gives you time-ordered UUIDs**
Sorting records by their UUID primary key is approximately the same as sorting by creation time. This is what makes cursor pagination keyed on `(created_at, id)` both correct and efficient — the composite index is naturally ordered.

---

## Technical Debt Tracker

Items to address in future Epics:

| Item | Priority | Target Epic |
|------|----------|-------------|
| Wire `init_db()` into app lifespan | High | EP-03 |
| Add FK constraint `deleted_by → users.id` | High | EP-03 (Users migration) |
| Type `extra_filters` as `ColumnElement[bool] | None` | Medium | EP-03 cleanup |
| Add query timeout via `command_timeout` | Medium | EP-04 |
| HMAC-sign cursor tokens for public API | Low | EP-05 |
| Sanitize DB error messages in health endpoint | Low | EP-04 |
| Remove backward-compat shims after import refactor | Low | EP-05+ |

---

*Document maintained by the AI FinOps Engineering team.*  
*Last updated: EP-02 completion.*
