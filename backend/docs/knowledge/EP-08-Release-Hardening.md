# EP-08 Release Hardening — Sprint Report

**Date:** 2026-06-29  
**Branch:** `claude/ai-finops-ep-01-s4d42x`  
**Sprint:** EP-08 Release Hardening — resolves findings from the EP-08 Engineering Review

---

## Summary

All five findings from the EP-08 Engineering Review have been resolved or formally documented. The two HIGH-severity blockers (REV-01, REV-02) are fully corrected. The two MEDIUM findings (REV-03, REV-04) are resolved. The LOW finding (REV-05) is formally documented as a deferred stop condition with a clear comment in the production code.

**Test results:** 775 passed, 30 skipped (DB integration tests), 0 failed.  
**New tests added:** 1 (Anthropic logging verification — `test_get_usage_logs_warning_on_api_error`)

---

## Findings Resolved

### RH-01 — Dead Test Import Removed (REV-01)

**Finding:** `from unittest.mock import MagicMock` was present in `app/api/v1/usage.py` inside `_run_collection_sync()`. The `MagicMock` name was imported but never referenced in the function body.

**Change:** Removed line 126 (`from unittest.mock import MagicMock`) from `_run_collection_sync()`.

**File changed:** `app/api/v1/usage.py`

No functional change — `MagicMock` was never called. The removal eliminates a test-only dependency from production application code.

---

### RH-02 — Anthropic Provider Failure Now Logged (REV-02)

**Finding:** The Anthropic `get_usage()` adapter caught all exceptions and returned an empty `UsagePage` with no log output. Transient network failures, revoked API keys, and programming errors were all silently swallowed, making data loss indistinguishable from a legitimately empty usage period.

**Change:** Added `structlog` import and `log = structlog.get_logger(__name__)` to `app/providers/adapters/anthropic.py`. The exception handler now emits a structured WARNING before returning the empty page:

```python
except Exception as exc:
    log.warning(
        "anthropic_usage_api_unavailable",
        error_type=type(exc).__name__,
        error=str(exc),
    )
    return UsagePage()
```

The graceful fallback behavior is preserved — the collection run is not aborted. The warning log gives operators the signal to distinguish expected unavailability (e.g., account lacks admin API access) from unexpected failures (network errors, revoked keys).

**Files changed:** `app/providers/adapters/anthropic.py`

**Credentials:** The `error` field contains `str(exc)`, which may include the error message from the HTTP client but never the API key value. The `error_type` field contains the exception class name only.

**New test:** `TestAnthropicAdapterGetUsage::test_get_usage_logs_warning_on_api_error` — verifies that on API failure, a `warning`-level structlog event named `anthropic_usage_api_unavailable` is emitted with `error_type` and `error` fields.

---

### RH-03 — Stub GET Endpoints Return HTTP 501 (REV-03)

**Finding:** Six GET endpoints (`/events`, `/events/{id}`, `/runs`, `/runs/{id}`, `/checkpoints`, `/providers/{provider}/status`) were stubs. Of these, the four list/status endpoints returned HTTP 200 with empty or zero-state responses, creating a false impression that the database had no data when in fact no database query was executed. The two single-record endpoints (`/events/{id}`, `/runs/{id}`) already returned honest 404 responses.

**Change:** The four misleading 200 endpoints now raise `HTTPException(501)`:
- `GET /usage/events` → HTTP 501
- `GET /usage/runs` → HTTP 501
- `GET /usage/checkpoints` → HTTP 501
- `GET /usage/providers/{provider}/status` → HTTP 501

The single-record 404 endpoints (`/events/{id}`, `/runs/{id}`) are unchanged — their 404 responses remain honest stubs.

Each 501 endpoint retains its `response_model` declaration (so OpenAPI documents the shape of the future EP-09 response), adds a `responses={501: ...}` annotation, and includes an updated summary tagged `[EP-09]` to signal that implementation is pending.

**File changed:** `app/api/v1/usage.py`

**Tests updated:** 4 existing tests renamed and updated to assert HTTP 501:
- `test_list_events_returns_empty` → `test_list_events_returns_501`
- `test_list_runs_returns_empty` → `test_list_runs_returns_501`
- `test_list_checkpoints_returns_empty` → `test_list_checkpoints_returns_501`
- `test_provider_status_openai` → `test_provider_status_openai_returns_501`

---

### RH-04 — Migration Enum Names Aligned with ORM (REV-04)

**Finding:** The Alembic migration `e6f7a8b9c0d1` created PostgreSQL enum types named `collectionrunstatus` and `collectiontrigger`. The ORM models declared `SQLEnum(..., name="collection_run_status")` and `SQLEnum(..., name="collection_trigger")` — names with underscores. While this mismatch did not cause runtime failures (SQLAlchemy maps Python enum values, not type names, during queries), future migrations that reference these type names by string would fail if the wrong name was used.

**Change:** Updated the migration to use the ORM-declared names:

```python
# Before:
sa.Enum("pending", "running", ..., name="collectionrunstatus")
sa.Enum("manual", "scheduled", name="collectiontrigger")

# After:
sa.Enum("pending", "running", ..., name="collection_run_status")
sa.Enum("manual", "scheduled", name="collection_trigger")
```

The downgrade `DROP TYPE` statements were updated accordingly:
```python
op.execute("DROP TYPE IF EXISTS collection_run_status")
op.execute("DROP TYPE IF EXISTS collection_trigger")
```

**File changed:** `migrations/versions/20260629_0800_e6f7a8b9c0d1_ep08_usage_collection.py`

**Safety:** No production database has been migrated with the original revision. The migration was updated in-place. Any developer environment that ran the original migration must drop and re-create the EP-08 tables or manually rename the enum types before applying new migrations.

---

### RH-05 — _run_collection_sync Documented as EP-09 Deferred (REV-05)

**Finding (LOW):** `_run_collection_sync()` called `adapter.get_usage()` and counted events/pages but did not persist anything to the database. The function returned a transient in-memory `UsageCollectionRun` object that appeared in the 202 response but was never saved. This was a documented EP-08 stop condition, but the code contained no in-code explanation.

**Change:** The docstring of `_run_collection_sync()` was expanded with an explicit EP-08 stop condition note:

```python
async def _run_collection_sync(*, provider: str, body: CollectUsageRequest) -> object:
    """Run collection synchronously and return an in-memory CollectionRun record.

    EP-08 STOP CONDITION: This function calls the provider adapter to count
    pages and events but does NOT persist anything to the database.  Full
    DB-backed persistence (via UsageCollectionService and an injected session)
    is deferred to EP-09 ...
    """
```

No functional change. No new tests.

---

## Code Quality Scan Results (RH-07)

The following checks were performed across all EP-08 production files (`app/usage/`, `app/api/v1/usage.py`, `app/providers/adapters/`, `app/repositories/usage_*.py`, `app/models/usage*.py`, `migrations/versions/...ep08...`):

| Check | Result |
|-------|--------|
| Test-only imports (`unittest`, `MagicMock`, `pytest`, `patch`) | ✅ None remaining after RH-01 |
| `print()` statements | ✅ None found |
| `pdb` / `breakpoint()` calls | ✅ None found |
| Commented-out code blocks | ✅ None found |
| TODO / FIXME / HACK / XXX markers | ✅ None found |
| Silent exception handlers without logging | ✅ Resolved by RH-02 |
| Unreachable code | ✅ None found |
| Duplicate logic | ✅ None found |

---

## Files Changed

| File | Change |
|------|--------|
| `app/providers/adapters/anthropic.py` | Added structlog import, logger, warning on exception |
| `app/api/v1/usage.py` | Removed MagicMock import; 4 stubs → 501; expanded docstring |
| `migrations/versions/20260629_0800_e6f7a8b9c0d1_ep08_usage_collection.py` | Aligned enum type names |
| `tests/test_ep08.py` | Updated 4 stub tests; added 1 Anthropic logging test |
| `docs/knowledge/EP-08-Knowledge-Transfer.md` | Updated gotchas section |
| `docs/knowledge/EP-08-Architecture-Review.md` | All findings marked resolved |
| `docs/knowledge/EP-08-Production-Readiness.md` | PRR-02, PRR-05 marked resolved |
| `docs/architecture/ARCHITECTURE_CHANGELOG.md` | Added [0.8.2] release hardening entry |

---

## Remaining EP-09 Prerequisites

The following items were identified in the EP-08 Engineering Review and are NOT part of this hardening sprint. They are deferred to EP-09 by design:

| ID | Item |
|----|------|
| G-03 | JWT authentication on collection trigger endpoints |
| G-04 | Inject DB session into `_run_collection_sync` (use `UsageCollectionService`) |
| G-05 | Implement GET query endpoints with real DB queries (replacing 501 stubs) |
| G-08 | Mark stale RUNNING runs as FAILED on service startup |
| G-09 | Implement batch upsert for `UsageEventRepository` |
| G-10 | Wire `ProviderUsageSummary` population into collection pipeline |
| G-11 | Add Prometheus metrics (events_collected, duration, failures) |
| G-12 | TTL eviction for completed tasks in `BackgroundCollectionFramework` |

---

## Final Decision

**EP-08 is approved and frozen. The project is ready to begin EP-09 (Cost & Analytics Engine).**
