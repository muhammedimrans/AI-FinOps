# SQLAlchemy Relationship Loading Strategy

| Field | Value |
|---|---|
| **Audience** | Backend engineers contributing to AI FinOps |
| **Applies to** | All SQLAlchemy ORM relationships in this codebase |
| **Status** | Enforced as of EP-03.5 |

---

## The Problem

SQLAlchemy's default `lazy="select"` loading strategy emits a new SQL query the
first time you access a relationship attribute. In synchronous code this is
transparent. In **async SQLAlchemy** it is catastrophic:

```python
# WRONG — crashes with MissingGreenlet in async context
org = await repo.get(org_id)
projects = org.projects  # Triggers a synchronous SQL query → MissingGreenlet
```

The error message is:
```
sqlalchemy.exc.MissingGreenlet: greenlet_spawn has not been called;
can't call await_only() here. Was IO attempted in an unexpected place?
```

This crash is confusing because it doesn't mention SQL at all. The root cause is
that the asyncpg driver requires async I/O, and lazy loading tries to do
synchronous I/O.

---

## The Policy

**All relationships in AI FinOps use `lazy="raise"`.**

With `lazy="raise"`, accessing an unloaded relationship raises
`sqlalchemy.exc.InvalidRequestError` immediately with a clear message:

```
InvalidRequestError: 'Organization.projects' is not available due to lazy='raise'
```

This fails loudly and early instead of crashing with a confusing greenlet error
at runtime, or worse, silently executing synchronous I/O in a sync-compatible
driver.

**This means: you must always explicitly load relationships before accessing them.**

---

## How to Load Relationships

### selectinload() — the default choice

Use `selectinload()` for collections (one-to-many). It emits a second `SELECT IN`
query to load all children in one round-trip:

```python
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.models.organization import Organization

stmt = (
    select(Organization)
    .where(Organization.id == org_id)
    .options(selectinload(Organization.projects))
)
result = await session.execute(stmt)
org = result.scalar_one()

# Now safe — projects were loaded eagerly
print(org.projects)  # list of Project instances
```

**When to use selectinload:**
- Loading a collection (one-to-many)
- When you need the parent and its children separately (e.g., pagination of children)
- When the parent has many relationships and you only need some of them

### joinedload() — use for single objects

Use `joinedload()` for scalar relationships (many-to-one or optional one-to-one).
It emits a SQL JOIN to load the related object in the same query:

```python
from sqlalchemy.orm import joinedload
from app.models.project import Project

stmt = (
    select(Project)
    .where(Project.id == project_id)
    .options(joinedload(Project.organization))
)
result = await session.execute(stmt)
proj = result.scalar_one()

print(proj.organization.name)  # safe — loaded via JOIN
```

**When to use joinedload:**
- Loading a scalar relationship (many-to-one, like `Project.organization`)
- When you always need both objects and want a single round-trip
- For optional relationships where you want `None` for missing parents

**Warning:** Using `joinedload()` on a collection (one-to-many) can produce
duplicate rows. Always use `selectinload()` for collections.

### Multiple relationships at once

You can chain multiple loading options:

```python
stmt = (
    select(Organization)
    .where(Organization.id == org_id)
    .options(
        selectinload(Organization.projects),
        selectinload(Organization.memberships),
        selectinload(Organization.provider_connections),
    )
)
```

Or use `contains_eager()` when you've already done a JOIN in the query:

```python
from sqlalchemy.orm import contains_eager

stmt = (
    select(Organization)
    .join(Organization.projects)
    .options(contains_eager(Organization.projects))
    .where(Project.environment == "production")
)
```

### raiseload() for explicitly-unwanted relationships

If you want to assert that certain relationships must NEVER be loaded (e.g., to
prevent N+1 queries in a loop), use `raiseload()`:

```python
from sqlalchemy.orm import raiseload, selectinload

stmt = (
    select(Organization)
    .options(
        selectinload(Organization.projects),
        raiseload("*"),  # Raise on any other relationship access
    )
)
```

---

## Strategy Selection Guide

| Relationship type | Recommended strategy | Reason |
|---|---|---|
| One-to-many collection | `selectinload()` | Avoids cartesian product |
| Many-to-one (FK parent) | `joinedload()` | Single round-trip, no duplicates |
| Optional many-to-one | `joinedload()` | Handles NULL FK correctly |
| Nested collections (1 deep) | `selectinload()` on each level | Clean and readable |
| When relationship is never needed | `raiseload("*")` | Prevents accidental N+1 |

---

## Common Mistakes

### Mistake 1: Accessing relationship in a loop

```python
# WRONG — N+1 queries if lazy loading were allowed; raises with lazy="raise"
projects = await proj_repo.list_by_org(org_id)
for proj in projects.items:
    print(proj.organization.name)  # Each access would be a separate query
```

```python
# CORRECT — one query for projects, one for organizations
stmt = (
    select(Project)
    .where(Project.organization_id == org_id, Project.deleted_at.is_(None))
    .options(joinedload(Project.organization))
)
```

### Mistake 2: Accessing relationship after session closes

```python
# WRONG — session is gone when accessing relationship
async with session_factory() as session:
    org = await repo.get(org_id)
# Session is closed here ↑

projects = org.projects  # Even with lazy="select" this would fail; "raise" makes it obvious
```

```python
# CORRECT — load relationships before session closes
async with session_factory() as session:
    stmt = select(Organization).where(...).options(selectinload(Organization.projects))
    org = (await session.execute(stmt)).scalar_one()
    return org.projects  # Safe — returned while session is open
```

### Mistake 3: Using joinedload() on a collection

```python
# WRONG — produces duplicate rows for orgs with multiple projects
stmt = select(Organization).options(joinedload(Organization.projects))
result = await session.execute(stmt)
orgs = result.scalars().all()  # May contain duplicate org rows!
```

```python
# CORRECT
stmt = select(Organization).options(selectinload(Organization.projects))
result = await session.execute(stmt)
orgs = result.scalars().all()  # Correct, no duplicates
```

---

## Passive Deletes

Organization's three collections (projects, memberships, provider_connections)
also set `passive_deletes=True`:

```python
projects: Mapped[list[Project]] = relationship(
    "Project",
    cascade="all, delete-orphan",
    lazy="raise",
    passive_deletes=True,  # ← rely on DB's ON DELETE CASCADE
)
```

Without `passive_deletes=True`, SQLAlchemy would try to load the entire collection
into Python before cascade-deleting, which requires an eager load. With it,
SQLAlchemy trusts the database FK constraint to handle deletion. Since the
migrations declare `ON DELETE CASCADE` on all FK constraints from child tables
to `organizations.id`, this is safe and correct.

**Implication:** When hard-deleting an Organization in an admin context, you do
NOT need to load projects/memberships/provider_connections first. The database
handles the cascade.

---

## Testing Relationships

Unit tests (mock session) should NOT test relationship loading — mocks bypass
SQLAlchemy's attribute machinery. Test relationship loading in integration tests:

```python
@pytest.mark.integration
async def test_selectinload_loads_projects(db_session):
    org = ...  # create org with projects
    stmt = select(Organization).options(selectinload(Organization.projects)).where(...)
    loaded = (await db_session.execute(stmt)).scalar_one()
    assert len(loaded.projects) > 0  # relationship is loaded and accessible
```

See `tests/integration/test_repositories.py` for complete examples.
