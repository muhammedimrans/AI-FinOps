# EP-08 Knowledge Transfer — Usage Collection Engine

## Overview

EP-08 implements the **Usage Collection Engine** (F-041 through F-049): the pipeline that fetches, normalizes, deduplicates, and persists AI provider usage data into the database.

## Key Concepts

### NormalizedUsageEvent (F-041)

The canonical, provider-agnostic usage record. Lives in `app/providers/models.py`:

```python
class NormalizedUsageEvent(BaseModel):
    provider_request_id: str   # dedup key — SHA1 hash for aggregated data
    provider: str
    model: str
    timestamp: datetime
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cached_tokens: int | None
    request_count: int
    metadata: dict[str, Any]
    raw_payload: dict[str, Any]
```

### UsagePage (F-042)

Paginated provider response. Used by `get_usage()` on all adapters:

```python
class UsagePage(BaseModel):
    events: list[NormalizedUsageEvent]
    next_cursor: str | None
    has_more: bool
```

### Normalizers (F-042)

Convert raw provider API responses to `NormalizedUsageEvent`. Two implementations:

| Class | Provider | API endpoint |
|-------|----------|--------------|
| `OpenAIUsageNormalizer` | OpenAI | `GET /v1/organization/usage/completions` |
| `AnthropicUsageNormalizer` | Anthropic | `GET /v1/usage` |

**Dedup hash**: OpenAI returns aggregated data without per-request IDs. A deterministic SHA1 hash of `(provider, model, start_time)` is used as `provider_request_id`:

```python
def _dedup_hash(*parts: str) -> str:
    return hashlib.sha1(":".join(parts).encode(), usedforsecurity=False).hexdigest()
```

### Validator (F-048)

`UsageEventValidator` enforces quality rules before persistence:
- Required strings: `provider_request_id`, `provider`, `model`
- Timestamp not more than 300 seconds in the future
- Token counts ≥ 0; `request_count` ≥ 1
- `cached_tokens` ≤ `prompt_tokens`

Invalid events are skipped (counted in `events_failed`) — they do not abort the collection run.

### Database Models (F-043, F-044, F-045)

Four new tables, all following `BaseModel` (UUIDv7 PK, soft-delete, cursor index):

| Table | Model | Purpose |
|-------|-------|---------|
| `usage_collection_runs` | `UsageCollectionRun` | Audit trail for each collection pass |
| `usage_events` | `UsageEvent` | Normalized per-request records |
| `usage_collection_checkpoints` | `UsageCollectionCheckpoint` | Incremental state for resumed collection |
| `provider_usage_summaries` | `ProviderUsageSummary` | Aggregated token totals by model/period |

**FK ordering** in `app/models/__init__.py`:
`UsageCollectionRun` → `UsageEvent`, `UsageCollectionCheckpoint` (both have FK to runs)

### Idempotent Upserts

All three event tables use `pg_insert().on_conflict_do_update()`:

| Table | Unique constraint |
|-------|-------------------|
| `usage_events` | `uq_usage_events_dedup` on `(organization_id, provider, provider_request_id)` |
| `usage_collection_checkpoints` | `uq_usage_checkpoints_org_provider_connection` (DEFERRABLE) |
| `provider_usage_summaries` | `uq_provider_usage_summaries` |

### UsageCollectionService (F-046)

Orchestrates the full collection pipeline for one provider:

1. Create `UsageCollectionRun` (status=RUNNING)
2. Load checkpoint → determine `effective_start` date and initial cursor
3. Build adapter via `ProviderFactory(registry).create(config)`
4. Paginate: `adapter.get_usage(start, end, cursor=cursor, limit=page_limit)`
5. Validate + upsert events per page
6. Update checkpoint after each page (mid-range resume support)
7. Mark run COMPLETED or FAILED

Checkpoint enables **incremental collection**: on subsequent runs, only events since `last_collected_at` are fetched.

### BackgroundCollectionFramework (F-047)

Lightweight asyncio-based task manager. No scheduler (EP-09 will add scheduling):

```python
framework = BackgroundCollectionFramework(session_factory, max_concurrent=5)
task_id = await framework.submit(organization_id=..., provider="openai", ...)
status  = framework.get_status(task_id)
await framework.cancel(task_id)
```

In-memory state only — resets on restart.

### REST API (F-049)

Mounted at `/v1/usage`:

| Method | Path | Description |
|--------|------|-------------|
| POST | `/collect` | Trigger collection for all production providers |
| POST | `/collect/{provider}` | Trigger for a specific provider |
| GET | `/events` | List usage events (paginated stub) |
| GET | `/events/{id}` | Get single event (404 stub) |
| GET | `/runs` | List collection runs (paginated stub) |
| GET | `/runs/{id}` | Get single run (404 stub) |
| GET | `/checkpoints` | List checkpoints (paginated stub) |
| GET | `/providers/{provider}/status` | Provider collection status (stub) |

Production-ready providers: `openai`, `anthropic`. Others return 404.

Query endpoints are stubs pending AppContainer DB session injection (EP-09).

## Gotchas

1. **`metadata` column name conflict**: SQLAlchemy's declarative `Base` reserves `metadata` as a class attribute. The ORM column is mapped as `event_metadata` (Python name) → `"metadata"` (DB column). The upsert uses `UsageEvent.__table__` (table-level insert) to avoid ORM attribute resolution.

2. **Anthropic usage API is optional**: Anthropic's admin usage endpoint may not be universally available. The adapter catches all exceptions and returns an empty `UsagePage` rather than failing the collection run.

3. **Lazy repo imports in service**: `UsageCollectionService.collect()` imports repo classes inside the method body to avoid circular imports. Tests must patch at the repo module path, not `app.usage.service.*`.

4. **Checkpoint deferrable constraint**: `uq_usage_checkpoints_org_provider_connection` is `DEFERRABLE INITIALLY DEFERRED` to avoid within-transaction constraint violations during upsert.
