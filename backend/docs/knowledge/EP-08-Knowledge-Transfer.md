# EP-08 Knowledge Transfer — Usage Collection Engine

**Date:** 2026-06-29  
**Features:** F-041 through F-049  
**Status:** Complete — pending architecture review before EP-09

---

## 1. Overview and Purpose

EP-08 implements the **Usage Collection Engine** — the pipeline responsible for fetching AI provider usage data, normalizing it into a provider-agnostic format, validating it, deduplicating it, and persisting it to the database for downstream cost and analytics processing.

### Scope

| Feature | Description |
|---------|-------------|
| F-041 | `NormalizedUsageEvent` and `UsagePage` Pydantic models |
| F-042 | `get_usage()` abstract method on `AIProvider`; adapter implementations; normalizers |
| F-043 | `UsageCollectionRun` ORM model and repository |
| F-044 | `UsageEvent` ORM model and repository |
| F-045 | `UsageCollectionCheckpoint` and `ProviderUsageSummary` ORM models and repositories |
| F-046 | `UsageCollectionService` orchestration |
| F-047 | `BackgroundCollectionFramework` asyncio task manager |
| F-048 | `UsageEventValidator` data quality enforcement |
| F-049 | REST API (8 endpoints at `/v1/usage`) |

### What is NOT in scope for EP-08

- Pricing engine and cost calculations (EP-09)
- Analytics dashboards (EP-10)
- Scheduled background jobs (EP-09 will add the scheduler)
- JWT-based authentication on collection endpoints
- Database session injection into GET query endpoints (EP-09)

---

## 2. Data Flow

```
Provider API
    │
    ▼
get_usage() on adapter          ← F-042
    │  returns UsagePage
    ▼
UsageCollectionService.collect()  ← F-046
    │
    ├─► UsageEventValidator.validate()  ← F-048  (invalid → skip + log)
    │
    ├─► _build_orm_event()
    │
    ├─► UsageEventRepository.upsert()   ← F-044  (ON CONFLICT DO UPDATE)
    │
    ├─► UsageCollectionCheckpointRepository.upsert()  ← F-045  (per page)
    │
    └─► UsageCollectionRunRepository.update()  ← F-043  (COMPLETED / FAILED)
```

The background framework (`BackgroundCollectionFramework`) wraps `collect()` in an asyncio task with semaphore-limited concurrency. The REST API triggers either synchronous or background collection.

---

## 3. NormalizedUsageEvent (F-041)

The canonical, provider-agnostic usage record. Lives in `app/providers/models.py`:

```python
class NormalizedUsageEvent(BaseModel):
    provider_request_id: str   # dedup key — SHA1 hash for aggregated data, raw ID for per-request APIs
    provider: str              # "openai", "anthropic", etc.
    model: str                 # model identifier string
    timestamp: datetime        # UTC event timestamp
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cached_tokens: int | None  # optional — None means not reported
    request_count: int         # aggregated request count (≥ 1)
    metadata: dict[str, Any]   # provider-specific extra fields
    raw_payload: dict[str, Any] # full original API response item
```

**Key invariant:** `provider_request_id` is the dedup key. It must be stable across repeated calls for the same event. Providers that return per-request IDs (Anthropic) use them directly. Providers that return aggregated records (OpenAI) use a deterministic SHA1 hash.

---

## 4. UsagePage (F-042)

Paginated provider response wrapper. Used as the return type for all `get_usage()` implementations:

```python
class UsagePage(BaseModel):
    events: list[NormalizedUsageEvent]
    next_cursor: str | None     # opaque cursor for the next page
    has_more: bool              # False → last page; stop paginating
```

**Stub adapters** (Azure, Google, Grok, Ollama, OpenRouter) return `UsagePage()` — empty events list, `has_more=False`. This satisfies the interface contract without raising `NotImplementedError`.

---

## 5. get_usage() Interface (F-042)

`AIProvider` abstract method signature:

```python
async def get_usage(
    self,
    start_date: datetime,
    end_date: datetime,
    *,
    cursor: str | None = None,
    limit: int = 100,
) -> UsagePage: ...
```

All 7 adapters satisfy this interface. The signature was promoted from a stub in EP-06.5 to a full abstract method in EP-08.

---

## 6. Usage Normalizers (F-042)

### Protocol

`UsageNormalizer` is a `runtime_checkable` structural Protocol (`app/usage/normalizer.py`):

```python
@runtime_checkable
class UsageNormalizer(Protocol):
    @property
    def provider_name(self) -> str: ...
    def normalize(self, raw: dict[str, Any]) -> NormalizedUsageEvent: ...
```

### Dedup Hash

```python
def _dedup_hash(*parts: str) -> str:
    payload = ":".join(parts)
    return hashlib.sha1(payload.encode(), usedforsecurity=False).hexdigest()
```

Returns a 40-character hex digest. `usedforsecurity=False` suppresses FIPS warnings — this hash is used only for deduplication, not security.

### OpenAI Normalizer

Input: `GET /v1/organization/usage/completions` response item.

```python
# Raw shape:
{
    "start_time": 1234567890,     # UNIX timestamp
    "model": "gpt-4o",
    "input_tokens": 1000,
    "output_tokens": 500,
    "num_model_requests": 1,
    "cached_input_tokens": 200    # optional
}
```

`provider_request_id` = `raw.get("id") or _dedup_hash("openai", model, str(start_time))`

Token mapping: `prompt_tokens = input_tokens`, `completion_tokens = output_tokens`, `total_tokens = input + output`, `cached_tokens = cached_input_tokens`.

### Anthropic Normalizer

Input: `GET /v1/usage` admin API response item.

```python
# Raw shape:
{
    "id": "req_xxx",                              # optional per-request ID
    "model": "claude-3-5-sonnet-20241022",
    "created_at": "2024-01-01T00:00:00Z",
    "input_tokens": 1000,
    "output_tokens": 500,
    "cache_read_input_tokens": 200,               # optional
    "num_requests": 1
}
```

`provider_request_id` = `raw.get("id") or _dedup_hash("anthropic", model, created_at_str)`

Handles ISO-8601 with `Z` suffix via `.replace("Z", "+00:00")`.

### NormalizerRegistry

```python
registry = NormalizerRegistry()
registry.register(OpenAIUsageNormalizer())
registry.register(AnthropicUsageNormalizer())
```

Note: The normalizer registry is not used by `UsageCollectionService` — the service delegates normalization to the adapter's `get_usage()` method. The normalizer classes are used internally by the adapter implementations. The `NormalizerRegistry` is available for external callers or future EP-09 use.

---

## 7. Adapter Implementations (F-042)

### OpenAI (app/providers/adapters/openai.py)

Calls `GET /v1/organization/usage/completions` with pagination. Parameters:
- `start_time` / `end_time` — UNIX timestamps derived from `start_date` / `end_date`
- `after` — cursor parameter for next-page requests
- `limit` — page size

Response contains `data` list and `has_more` boolean. Each item is normalized via `OpenAIUsageNormalizer`. If the API returns a `next_page` or `next_cursor` field, it is passed through as `UsagePage.next_cursor`.

### Anthropic (app/providers/adapters/anthropic.py)

Calls `GET /v1/usage` with date filtering. Requires special admin-level API permissions that may not be available on all accounts.

**Critical design decision:** The adapter catches ALL exceptions in `get_usage()` and returns `UsagePage()` (empty). This prevents Anthropic's optional usage API from causing collection failures on accounts that don't have access.

```python
except Exception:
    return UsagePage()
```

This is intentional but has observability implications — see Architecture Review section REV-02.

### Stub Adapters

Azure, Google, Grok, Ollama, OpenRouter all return `UsagePage()` immediately. They satisfy the interface without raising `NotImplementedError`.

---

## 8. Database Models (F-043, F-044, F-045)

All four models inherit `BaseModel(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin)` providing UUIDv7 primary keys, `created_at`/`updated_at` timestamps, and `deleted_at` soft-delete support.

### UsageCollectionRun

**Table:** `usage_collection_runs`  
**Purpose:** Audit trail — one row per collection pass.

```python
class CollectionRunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class CollectionTrigger(StrEnum):
    MANUAL = "manual"
    SCHEDULED = "scheduled"
    WEBHOOK = "webhook"
```

**SQLEnum names:** `collection_run_status`, `collection_trigger` (lowercase with underscores, matching the Python StrEnum class names).

**Migration enum names:** `collectionrunstatus`, `collectiontrigger` (lowercase, no underscores).

**Enum type names (aligned in hardening sprint):** The migration and ORM both use `collection_run_status` and `collection_trigger` (with underscores). Future migrations that reference these enum types must use these exact names.

Key columns:
- `organization_id` — UUID, required (no FK — EP-09 will add org table)
- `provider` — VARCHAR(64)
- `provider_connection_id` — UUID, nullable (future FK to provider connections table)
- `status` — `CollectionRunStatus` enum
- `triggered_by` — `CollectionTrigger` enum
- `started_at` / `completed_at` — UTC timestamps
- `collection_start` / `collection_end` — date range collected
- `events_collected` / `events_failed` / `pages_fetched` — counters
- `error_message` — TEXT, nullable
- `collection_config` — JSONB

`external_id` is a computed `@property` returning `str(self.id)` — it has no setter.

### UsageEvent

**Table:** `usage_events`

**⚠ Critical workaround:** SQLAlchemy's `DeclarativeBase` reserves `metadata` as a class attribute for `MetaData`. The `metadata` DB column is mapped as `event_metadata` Python attribute:

```python
event_metadata: Mapped[dict[str, Any]] = mapped_column(
    "metadata", JSONB, nullable=False, default=dict
)
```

The repository uses `UsageEvent.__table__` (table-level INSERT) for upserts to bypass ORM attribute resolution:

```python
tbl = UsageEvent.__table__
stmt = pg_insert(tbl).values(
    ...
    metadata=event.event_metadata,   # DB column name "metadata"
    ...
)
```

**Unique constraint:** `uq_usage_events_dedup` on `(organization_id, provider, provider_request_id)` — the dedup key.

Key columns:
- `organization_id` — UUID
- `project_id` — UUID, nullable
- `provider_connection_id` — UUID, nullable
- `collection_run_id` — UUID, nullable (FK to `usage_collection_runs.id`)
- `provider` — VARCHAR(64)
- `provider_request_id` — VARCHAR(256)
- `model` — VARCHAR(256)
- `timestamp` — TIMESTAMPTZ
- `request_count` — INTEGER
- `prompt_tokens` / `completion_tokens` / `total_tokens` — INTEGER
- `cached_tokens` — INTEGER, nullable
- `event_metadata` → `"metadata"` — JSONB
- `raw_provider_payload` — JSONB

### UsageCollectionCheckpoint

**Table:** `usage_collection_checkpoints`

**Purpose:** Incremental state — records the last successful collection position so subsequent runs only fetch new data.

**⚠ Deferrable constraint:** `uq_usage_checkpoints_org_provider_connection` is `DEFERRABLE INITIALLY DEFERRED`. This allows the upsert (INSERT ... ON CONFLICT DO UPDATE) to work within a transaction without mid-transaction constraint violations.

Key columns:
- `organization_id` — UUID
- `provider` — VARCHAR(64)
- `provider_connection_id` — UUID, nullable (part of the unique key)
- `last_collected_at` — TIMESTAMPTZ — used to compute `effective_start` on next run
- `cursor` — TEXT, nullable — resume cursor
- `last_run_id` — UUID (FK to `usage_collection_runs.id`)

### ProviderUsageSummary

**Table:** `provider_usage_summaries`

**Purpose:** Aggregated token totals by (organization, provider, model, period). Pre-computed for dashboard performance.

Key columns:
- `organization_id`, `provider`, `model` — grouping key
- `period_start` / `period_end` — aggregation window
- `total_prompt_tokens` / `total_completion_tokens` / `total_tokens` / `total_cached_tokens` — BigInteger
- `total_requests` / `total_events` — INTEGER
- `summary_metadata` — JSONB

**Unique constraint:** `uq_provider_usage_summaries` on `(organization_id, provider, model, period_start, period_end)`.

---

## 9. Repositories (F-043, F-044, F-045)

All repositories inherit `BaseRepository[T]` which provides:
- `create(entity)` — INSERT via ORM
- `get(id)` — SELECT by PK with soft-delete filter
- `list_page(organization_id, cursor, limit)` — cursor-paginated list
- `soft_delete(id)` — sets `deleted_at`
- `update(entity, **kwargs)` — ORM attribute update

### UsageEventRepository

Key method: `upsert(event: UsageEvent) -> UsageEvent`

```python
tbl = UsageEvent.__table__
stmt = (
    pg_insert(tbl)
    .values(id=event.id or uuid7(), ..., metadata=event.event_metadata, ...)
    .on_conflict_do_update(
        constraint="uq_usage_events_dedup",
        set_={
            "total_tokens": ...,
            "prompt_tokens": ...,
            "completion_tokens": ...,
            "cached_tokens": ...,
            "request_count": ...,
            "metadata": ...,
            "raw_provider_payload": ...,
            "updated_at": ...,
        }
    )
    .returning(tbl.c.id)
)
```

Additional query methods: `get_by_provider()`, `get_by_date_range()`, `get_by_model()`, `get_by_organization()`.

### UsageCollectionRunRepository

Lifecycle methods: `mark_completed()`, `mark_failed()`, `get_latest_run()`, `get_runs_by_status()`, `get_runs_by_provider()`.

Update method takes `**kwargs` and sets ORM attributes, then flushes.

### UsageCollectionCheckpointRepository

Key method: `get_by_org_provider(organization_id, provider, provider_connection_id) -> UsageCollectionCheckpoint | None`

Uses `scalar_one_or_none()` — NOT `scalars().first()`.

Upsert method: `upsert(organization_id, provider, ...) -> UsageCollectionCheckpoint`

⚠ The upsert has a secondary fallback path: after `pg_insert().on_conflict_do_update()`, the method calls `get_by_org_provider()` to retrieve the resulting record. If not found (should not happen after upsert), it creates a new record. This fallback path is defensive but redundant — the upsert guarantees a row exists.

### ProviderUsageSummaryRepository

Key method: `upsert_summary(summary: ProviderUsageSummary) -> ProviderUsageSummary`

Uses `on_conflict_do_update()` on `uq_provider_usage_summaries`.

---

## 10. UsageCollectionService (F-046)

**File:** `app/usage/service.py`

Orchestrates the complete pipeline for one provider and date range.

### Lazy Imports

Repositories are imported lazily inside `collect()` to avoid circular imports at module load time:

```python
async def collect(self, ...) -> UsageCollectionRun:
    from app.repositories.usage_collection_checkpoint_repository import (
        UsageCollectionCheckpointRepository,
    )
    from app.repositories.usage_collection_run_repository import UsageCollectionRunRepository
    from app.repositories.usage_event_repository import UsageEventRepository
    ...
```

**Test patching implication:** Tests must patch at the repository module path, not at `app.usage.service.*`:

```python
# WRONG — name doesn't exist at service module level at import time:
patch("app.usage.service.UsageCollectionRunRepository")

# CORRECT — patch the class in its defining module:
import app.repositories.usage_collection_run_repository as ucr_mod
ucr_mod.UsageCollectionRunRepository = MagicMock(return_value=mock_run_repo)
```

### Incremental Collection

On each run:
1. Load existing checkpoint → get `last_collected_at` and `cursor`
2. If `last_collected_at > start_date`, use it as `effective_start`
3. Paginate from `effective_start` to `end_date`
4. After each page, update checkpoint with new cursor (or clear if last page)
5. On last page, update `last_collected_at = end_date`

This means a run interrupted mid-pagination can resume from the last checkpoint page on retry.

### Error Handling

The service re-raises all exceptions after marking the run `FAILED`. The caller (API or background framework) receives the exception and handles it at the appropriate level.

---

## 11. BackgroundCollectionFramework (F-047)

**File:** `app/usage/background.py`

Lightweight asyncio task manager. No scheduler — callers trigger explicitly.

```python
framework = BackgroundCollectionFramework(session_factory, max_concurrent=5)
task_id = await framework.submit(organization_id=..., provider="openai", ...)
status = framework.get_status(task_id)           # returns dict or None
tasks = framework.list_tasks(provider="openai")  # filtered list
await framework.cancel(task_id)                  # returns True if cancelled
count = framework.running_count()
```

### Session Pattern

`_run_task()` calls `session = await self._session_factory()`, then uses `async with session.begin()`. The session factory must return a session whose `begin()` method returns an async context manager (standard SQLAlchemy `AsyncSession` behavior).

### In-Memory State

`_tasks: dict[uuid.UUID, CollectionTaskRecord]` — resets on process restart. Task records are never persisted to the database directly by the framework; persistence is done by `UsageCollectionService` through the `UsageCollectionRun` record.

### TaskStatus enum

```python
class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
```

---

## 12. REST API (F-049)

**File:** `app/api/v1/usage.py`  
**Router prefix:** `/v1/usage`

### Production-Ready Endpoints

| Method | Path | Status | Notes |
|--------|------|--------|-------|
| POST | `/collect` | **Production** | Synchronous; runs all providers; returns 202 |
| POST | `/collect/{provider}` | **Production** | Synchronous; 404 for unsupported providers |

### Stub Endpoints (EP-09 will implement)

| Method | Path | Status | Notes |
|--------|------|--------|-------|
| GET | `/events` | **Stub** | Returns `items=[], has_more=False` |
| GET | `/events/{event_id}` | **Stub** | Always returns 404 |
| GET | `/runs` | **Stub** | Returns `items=[], has_more=False` |
| GET | `/runs/{run_id}` | **Stub** | Always returns 404 |
| GET | `/checkpoints` | **Stub** | Returns `items=[], has_more=False` |
| GET | `/providers/{provider}/status` | **Stub** | Returns zero-state response |

### _run_collection_sync

The synchronous collection path in `_run_collection_sync()` does NOT persist to the database. It calls `adapter.get_usage()` to count events and pages, then constructs a `UsageCollectionRun` ORM object in memory (not saved to DB) to satisfy the response model. The response object is valid but transient.

This is an accepted EP-08 stop condition — full DB-backed collection with session injection is deferred to EP-09.

### Authentication

`organization_id` is a required query/body parameter. The docstring notes: "Production deployments should derive it from the JWT access token claims instead." There is no JWT authentication enforcement on any `/v1/usage` endpoint. This is a known gap — see Architecture Review REV-03.

### _COLLECTION_PROVIDERS

```python
_COLLECTION_PROVIDERS = frozenset({"openai", "anthropic"})
```

Requests for any other provider return HTTP 404. This list must be kept in sync with the providers that have real `get_usage()` implementations (not stubs).

### Import of unittest.mock in Production Code

`_run_collection_sync()` contains `from unittest.mock import MagicMock` — this import is present in the production API handler but `MagicMock` is not used anywhere in the function body. This is a dead import that should be removed.

---

## 13. Alembic Migration

**File:** `migrations/versions/20260629_0800_e6f7a8b9c0d1_ep08_usage_collection.py`  
**Revision:** `e6f7a8b9c0d1`  
**Revises:** `d5e6f7a8b9c0` (EP-07)

Creates 4 tables in dependency order:
1. `usage_collection_runs` (no FK dependencies among the 4 tables)
2. `usage_events`
3. `usage_collection_checkpoints`
4. `provider_usage_summaries`

Downgrade drops tables in reverse order, then drops enum types.

**Enum type name mismatch:** Migration creates `collectionrunstatus` and `collectiontrigger`; ORM's `SQLEnum(..., name="collection_run_status")` and `SQLEnum(..., name="collection_trigger")` use names with underscores. See REV-01 in Architecture Review.

---

## 14. Test Suite (F-049)

**File:** `tests/test_ep08.py` — 86 unit tests

Test classes and coverage:

| Class | Tests | Coverage |
|-------|-------|---------|
| `TestNormalizedUsageEvent` | Model validation, field constraints |
| `TestUsagePage` | Pagination model, defaults |
| `TestDedupHash` | SHA1 stability, determinism, multi-part |
| `TestOpenAIUsageNormalizer` | All field mappings, dedup fallback, edge cases |
| `TestAnthropicUsageNormalizer` | All field mappings, ISO timestamp parsing, ID fallback |
| `TestNormalizerRegistry` | CRUD, `get_normalizer_registry()` |
| `TestUsageEventValidator` | All 7 validation rules (required strings, timestamp, tokens) |
| `TestUsageEventRepository` | Upsert call execution |
| `TestUsageCollectionRunRepository` | Instantiation |
| `TestUsageCollectionCheckpointRepository` | `get_by_org_provider`, `scalar_one_or_none`, upsert |
| `TestUsageCollectionService` | collect_single_page, failure marking, validation failure counting |
| `TestBackgroundCollectionFramework` | submit, cancel, status, list, filter |
| `TestUsageAPI` | All 8 endpoints: 202, 404, 422 responses |
| `TestOpenAIAdapterGetUsage` | Mock `_build_client` context manager |
| `TestAnthropicAdapterGetUsage` | Graceful fallback on error |
| `TestStubAdapterGetUsage` | Azure, Google, Ollama return empty UsagePage |

**EP-06 test updates:** 7 `TestGetUsage` tests in `test_ep06.py` were updated:
- OpenAI/Anthropic: now expect `AuthenticationError` (real implementations attempt auth)
- Stub providers: now expect empty `UsagePage()` instead of `NotImplementedError`

---

## 15. Key Gotchas for EP-09

1. **`event_metadata` not `metadata`**: Any code that sets usage event metadata must use `event.event_metadata`, not `event.metadata`. The DB column name is `metadata`; the Python attribute is `event_metadata`.

2. **Table-level upsert for UsageEvent**: Must use `pg_insert(UsageEvent.__table__)`, not `pg_insert(UsageEvent)`. Using the ORM class resolves `metadata` to SQLAlchemy's `MetaData` object.

3. **Lazy repo imports in service**: Test patches must target the repository module path directly, not `app.usage.service.*`.

4. **Checkpoint `scalar_one_or_none()`**: The checkpoint repository uses `scalar_one_or_none()`, not `scalars().first()`. These are different SQLAlchemy async result methods.

5. **Anthropic silent failure**: Anthropic's `get_usage()` never raises. Empty response does not indicate success — it may indicate the usage API is unavailable. There is no logging on this path.

6. **`_run_collection_sync` does not persist to DB**: The API's synchronous collection path counts events but does not persist them. EP-09 must inject the AppContainer DB session to enable real persistence.

7. **Migration enum names**: `collectionrunstatus` / `collectiontrigger` in the migration differ from `collection_run_status` / `collection_trigger` in the ORM. Future migrations that reference these enum types must use the DB-level names (no underscores).

8. **`_run_collection_sync` does not persist to DB**: The API's synchronous collection path counts events but does not persist them. EP-09 must inject the AppContainer DB session to enable real persistence. The function docstring documents this explicitly as an EP-08 stop condition.
