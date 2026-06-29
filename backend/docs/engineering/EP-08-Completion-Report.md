# EP-08 Completion Report — Usage Collection Engine

**Date:** 2026-06-29  
**Branch:** `claude/ai-finops-ep-01-s4d42x`  
**Features:** F-041 through F-049

## Deliverables

### 1. Provider Models Extended (F-041, F-042)

`app/providers/models.py` — two new Pydantic v2 models:
- `NormalizedUsageEvent` — provider-agnostic event with dedup key, token counts, raw payload
- `UsagePage` — paginated response container for `get_usage()`

### 2. Provider Interface Updated (F-042)

`app/providers/interface.py` — `get_usage()` signature promoted from stub to abstract method returning `UsagePage`:

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

### 3. Provider Adapters Implemented (F-042)

| Adapter | Implementation |
|---------|---------------|
| `OpenAIProvider` | `GET /v1/organization/usage/completions` with pagination |
| `AnthropicProvider` | `GET /v1/usage` with graceful fallback on error |
| Azure, Google, Grok, Ollama, OpenRouter | Return empty `UsagePage()` |

### 4. Usage Normalizers (F-042)

`app/usage/normalizer.py`:
- `OpenAIUsageNormalizer` — handles aggregated OpenAI usage format
- `AnthropicUsageNormalizer` — handles Anthropic per-request format
- `_dedup_hash()` — SHA1 stable hash for aggregated dedup IDs
- `NormalizerRegistry` + `get_normalizer_registry()`

### 5. Usage Event Validator (F-048)

`app/usage/validator.py` — `UsageEventValidator` with full validation rule set.

### 6. Database Models (F-043, F-044, F-045)

Four new ORM models:
- `app/models/usage_collection_run.py`
- `app/models/usage_event.py`
- `app/models/usage_collection_checkpoint.py`
- `app/models/provider_usage_summary.py`

### 7. Repositories (F-043, F-044, F-045)

Four new repository classes with cursor pagination, filtered queries, and idempotent upserts:
- `UsageEventRepository`
- `UsageCollectionRunRepository`
- `UsageCollectionCheckpointRepository`
- `ProviderUsageSummaryRepository`

### 8. Collection Service (F-046)

`app/usage/service.py` — `UsageCollectionService` orchestrates the full pipeline with incremental checkpointing.

### 9. Background Framework (F-047)

`app/usage/background.py` — `BackgroundCollectionFramework` manages asyncio tasks with semaphore-limited concurrency.

### 10. REST API (F-049)

`app/api/v1/usage.py` — 8 endpoints mounted at `/v1/usage`.

### 11. Alembic Migration

`migrations/versions/20260629_0800_e6f7a8b9c0d1_ep08_usage_collection.py` — creates all 4 tables with indexes and constraints.

### 12. Test Suite (F-049)

`tests/test_ep08.py` — 86 unit tests covering all EP-08 features.

## Test Results

```
774 passed, 30 skipped, 5 warnings (0 failed)
```

EP-08 adds 86 new tests. 7 existing EP-06 `TestGetUsage` tests were updated to reflect the new `get_usage()` behavior (stubs replaced with real implementations).

## Architecture Decisions

### Metadata Column Rename

SQLAlchemy's `DeclarativeBase` reserves the class attribute `metadata` for `MetaData`. The `UsageEvent` model maps the `metadata` DB column to `event_metadata` as the Python attribute. The repository uses `UsageEvent.__table__` for the upsert INSERT to bypass ORM attribute resolution.

### Lazy Repository Imports

`UsageCollectionService.collect()` imports repository classes inside the method body. This avoids circular imports at startup but requires tests to patch at the repository module paths.

### Anthropic Fallback

The Anthropic adapter catches all exceptions in `get_usage()` and returns an empty `UsagePage`. Anthropic's admin usage API requires special account permissions and may not be available on all accounts.

## Stop Condition

Per the EP-08 specification:
- ✅ Usage Collection Engine (F-041–F-049) implemented
- ❌ Pricing engine NOT implemented
- ❌ Cost calculations NOT implemented  
- ❌ Scheduled background jobs NOT implemented
- ❌ Analytics dashboards NOT implemented

**Waiting for architecture review before EP-09.**
