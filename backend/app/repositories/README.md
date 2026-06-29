# app/repositories — Repository Layer

## Purpose

Implements the Repository pattern as the "Ports" layer in AI FinOps's
four-layer architecture. Repositories encapsulate all database I/O and
provide a clean, async interface to the service layer.

## Responsibilities

| File                  | Responsibility                                       |
|-----------------------|------------------------------------------------------|
| `base_repository.py`  | Generic `BaseRepository[T]` + cursor pagination      |
| `base.py`             | Backward-compatibility re-export shim                |

## Key Design Decisions

### Generic BaseRepository[T]
`BaseRepository` is parametrised on a concrete `BaseModel` subclass so
each entity repository inherits full CRUD without boilerplate:

```python
class OrganizationRepository(BaseRepository[Organization]):
    model = Organization
```

### Cursor-Based Pagination
All list operations use `CursorPage` with opaque base64-encoded tokens.
Cursors are keyed on `(created_at, id)` which maps to the
`ix_<table>_cursor` composite index added by `BaseModel`.

### Soft-Delete Filtering
`_active_query()` automatically adds `WHERE deleted_at IS NULL` to all
standard queries. Deleted records are only accessible via explicit
admin-level queries.

### No Session Management
Repositories receive an `AsyncSession` and flush changes; they never
commit or rollback. Transaction lifecycle is controlled by:
  - `get_session()` — FastAPI request scope
  - `managed_transaction()` — background jobs, batch ops

## Dependencies

- `app.db.mixins.BaseModel` — required T bound for typing
- `sqlalchemy.ext.asyncio.AsyncSession` — injected by the DI layer

## Future Implementation

As new business entities are added in later Epics, add their repositories here:

```python
# EP-03
from app.repositories.organization import OrganizationRepository
from app.repositories.user import UserRepository
```
