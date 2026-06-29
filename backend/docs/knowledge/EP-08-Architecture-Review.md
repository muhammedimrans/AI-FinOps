# EP-08 Architecture Review — Usage Collection Engine

**Date:** 2026-06-29  
**Reviewer:** Principal Software Architect / Staff Platform Engineer  
**Subject:** EP-08 Usage Collection Engine (F-041–F-049)  
**Branch:** `claude/ai-finops-ep-01-s4d42x`

---

## Executive Summary

EP-08 delivers a well-structured, provider-agnostic usage collection pipeline with sound incremental checkpointing, idempotent upserts, and correct observability instrumentation. The architecture is solid for a development/staging environment and meets the EP-08 specification.

Five findings are raised. Two are HIGH severity and must be resolved before any production traffic is handled. The remaining three are MEDIUM or LOW and can be resolved in EP-08.5 or tracked as EP-09 prerequisites.

**Score: 7.5 / 10** → **8.5 / 10 (post-hardening)**

**Decision: APPROVED WITH MINOR CHANGES** → **APPROVED AND FROZEN (post-hardening)**

All five findings were resolved in the EP-08 Release Hardening Sprint. See `docs/knowledge/EP-08-Release-Hardening.md` for the full resolution report.

---

## Architecture Strengths

### S-01 — Provider-Agnostic Pipeline Design

The service layer (`UsageCollectionService`) contains zero provider-specific logic. All provider differences are encapsulated behind the `get_usage()` → `NormalizedUsageEvent` boundary. Adding a new provider requires only: implementing `get_usage()` on the adapter and (optionally) a `UsageNormalizer`. The service, repositories, and API are unchanged.

### S-02 — Idempotent Upserts on All Persistence Paths

All three write paths use `pg_insert().on_conflict_do_update()`:
- `usage_events` on `uq_usage_events_dedup`
- `usage_collection_checkpoints` on `uq_usage_checkpoints_org_provider_connection`
- `provider_usage_summaries` on `uq_provider_usage_summaries`

Re-running the same date range is safe. This is the correct design for an eventually-consistent collection system.

### S-03 — Per-Page Checkpointing

The checkpoint is updated after every page, not only at the end of the collection run. This limits data loss on interruption to at most one page. The deferrable constraint on the checkpoint table is correctly used to support within-transaction upserts.

### S-04 — Deterministic Dedup Hash

The SHA1 dedup hash for aggregated provider data (OpenAI) is derived from `(provider, model, start_time)` — a stable, provider-provided aggregation key. Re-collecting the same aggregation window produces the same hash, guaranteeing idempotency even when the provider returns the same aggregated record across multiple API calls.

### S-05 — Structured Logging Throughout

All log calls use `structlog.get_logger(__name__)` with keyword context bindings (`organization_id`, `provider`, `run_id`, etc.). No `print()` statements. This satisfies the EP-07.5 requirement (PRR-05) and produces machine-parseable logs compatible with log aggregation pipelines.

### S-06 — Clean Separation of Background Framework from Service

`BackgroundCollectionFramework` is a thin asyncio task manager — it contains no business logic. `UsageCollectionService` contains all business logic and is testable without the background framework. This separation allows the scheduler (EP-09) to wrap the service in a different execution model without modifying the service.

### S-07 — Validator Fails Open (Skip, Don't Abort)

Invalid events are counted and skipped rather than aborting the collection run. This is correct for a usage collection system where one malformed record from the provider should not prevent thousands of valid records from being persisted.

---

## Findings

### REV-01 — HIGH: Production Code Contains `unittest.mock` Import

**File:** `app/api/v1/usage.py`, function `_run_collection_sync()`, line 127  
**Severity:** HIGH  
**Category:** Code Quality / Production Safety

```python
async def _run_collection_sync(*, provider: str, body: CollectUsageRequest) -> object:
    """Run collection synchronously (no DB session — mock-friendly for tests)."""
    from unittest.mock import MagicMock   # ← dead import in production code
    ...
    # MagicMock is not used anywhere in this function
```

`unittest.mock` is a test-only module from the standard library. Importing it in production application code is incorrect. While the import itself does not cause a runtime failure in CPython, it:
- Signals that this function was developed for tests and not properly cleaned up
- May trigger static analysis warnings in security scans
- Unnecessarily loads test infrastructure in production processes

The `MagicMock` identifier is imported but never referenced in the function body.

**Resolution:** Remove line 127 (`from unittest.mock import MagicMock`).

---

### REV-02 — HIGH: Anthropic Usage Failure is Fully Silent

**File:** `app/providers/adapters/anthropic.py`, `get_usage()` method  
**Severity:** HIGH  
**Category:** Observability / Operational Reliability

The Anthropic adapter catches all exceptions and returns an empty `UsagePage` with no log message:

```python
except Exception:
    return UsagePage()
```

This means:
1. A transient network failure is indistinguishable from "no data" in the collection run metrics
2. An API key revocation is indistinguishable from "no data"
3. A programming error in the normalization path is swallowed
4. The collection run marks itself COMPLETED with `events_collected=0` — an operator cannot determine whether this is expected (empty period) or a failure

**Resolution:** Log a warning with the exception type and message before returning. The exception value must not be logged at a level that would trigger an alert for expected cases (e.g., accounts without admin usage API access), so `WARNING` with exception details is appropriate:

```python
except Exception as exc:
    log.warning(
        "anthropic_usage_api_unavailable",
        error_type=type(exc).__name__,
        error=str(exc),
    )
    return UsagePage()
```

This preserves the graceful fallback while giving operators the information to distinguish transient failures from permanent unavailability.

---

### REV-03 — MEDIUM: GET Query Endpoints are Hard Stubs with Misleading 200 Responses

**File:** `app/api/v1/usage.py`  
**Severity:** MEDIUM  
**Category:** API Contract / Developer Experience

Six of the eight endpoints (`GET /events`, `GET /events/{id}`, `GET /runs`, `GET /runs/{id}`, `GET /checkpoints`, `GET /providers/{provider}/status`) are stubs that always return empty data or 404 regardless of what records exist in the database.

A client calling `GET /v1/usage/events` after a successful collection will receive:
```json
{"items": [], "next_cursor": null, "has_more": false, "count": 0}
```

This is a `200 OK` response that misrepresents the system state. The collection run may have persisted thousands of events, but the API reports zero. This can cause:
- Integration partners building against these endpoints to ship broken integrations
- False confidence that an empty response means "no data collected"
- Difficulty debugging EP-08 behavior in staging without direct DB access

**Resolution options:**
1. Return `HTTP 501 Not Implemented` from stub endpoints (preferred — honest contract)
2. Document endpoints explicitly as `[STUB — EP-09]` in OpenAPI descriptions

Option 1 prevents misuse of the stubs as production endpoints. Option 2 is lower risk but still allows incorrect usage. EP-09 must replace these stubs with real DB-backed implementations.

---

### REV-04 — MEDIUM: Alembic Enum Type Name Mismatch

**File:** `migrations/versions/20260629_0800_e6f7a8b9c0d1_ep08_usage_collection.py`  
**Severity:** MEDIUM  
**Category:** Schema Consistency / Migration Safety

The migration creates PostgreSQL enum types:
```python
sa.Enum("running", "completed", "failed", "cancelled", name="collectionrunstatus")
sa.Enum("manual", "scheduled", "webhook", name="collectiontrigger")
```

The ORM models declare:
```python
SQLEnum(CollectionRunStatus, name="collection_run_status")
SQLEnum(CollectionTrigger, name="collection_trigger")
```

At runtime in PostgreSQL, SQLAlchemy uses the ORM-specified names when checking if types exist. When the ORM generates DDL for a fresh database, it will attempt to create `collection_run_status` and `collection_trigger`. In a migration-managed database where Alembic has already created `collectionrunstatus` and `collectiontrigger`, the ORM will create duplicate types with the underscore names — or, if Alembic marks them as already existing, the ORM will use the wrong names in queries.

This inconsistency is currently masked because:
1. Alembic-created tables reference the DB-level names directly
2. The ORM works with the Python enum values (not the type name) for reads

However, a future migration that references these types (e.g., to add a value or rename) must use the DB-level names without underscores. This will surprise future engineers and may cause migration failures.

**Resolution:** Align the migration enum names with the ORM-declared names by adding underscores:
```python
sa.Enum(..., name="collection_run_status")
sa.Enum(..., name="collection_trigger")
```
And update the corresponding `DROP TYPE` statements in the downgrade.

This requires a new migration or regenerating the EP-08 migration. Since no production database has been migrated yet, regenerating the migration is safe.

---

### REV-05 — LOW: `_run_collection_sync` Does Not Persist to Database

**File:** `app/api/v1/usage.py`, `_run_collection_sync()`  
**Severity:** LOW  
**Category:** Feature Completeness / EP-08 Stop Condition

The synchronous collection endpoint calls `adapter.get_usage()` and counts events, but constructs an in-memory `UsageCollectionRun` object without saving it to the database. No events are persisted. This is documented as an EP-08 stop condition ("Query endpoints are stubs pending AppContainer DB session injection (EP-09)").

This is correctly classified as a known limitation, not a bug. However, the consequence is that POST `/v1/usage/collect` and POST `/v1/usage/collect/{provider}` return a "successful" `CollectionRunResponse` with `events_collected > 0` while persisting nothing. A caller that subsequently queries `GET /v1/usage/events` will see `items=[]`.

**Resolution:** This finding is informational — it confirms the EP-08 stop condition is correctly documented. EP-09 MUST replace `_run_collection_sync` with `UsageCollectionService.collect()` using an injected database session before any collection data can be queried. The current endpoint signature and response model are correct and should be preserved.

---

## Architecture Decisions Reviewed

### ADR-08-01: SQLAlchemy `metadata` Column Workaround

**Decision:** Map the `metadata` DB column to `event_metadata` Python attribute; use `UsageEvent.__table__` for upsert operations.

**Review:** Correct. SQLAlchemy's `DeclarativeBase` reserves `metadata` unconditionally. The chosen approach is the standard workaround. The table-level upsert using `.__table__` is the documented approach for bypassing ORM attribute resolution. No alternative avoids this without renaming the DB column.

**Verdict:** Accepted.

### ADR-08-02: Anthropic Graceful Fallback

**Decision:** Catch all exceptions in `get_usage()` and return `UsagePage()`.

**Review:** The graceful fallback is justified — Anthropic's admin usage API is not universally available and an unavailable API should not block the collection run. However, the implementation is too silent (see REV-02). The decision to return an empty page is correct; the implementation must log the failure.

**Verdict:** Accepted with required change (REV-02).

### ADR-08-03: Lazy Repository Imports in Service

**Decision:** Import repository classes inside `UsageCollectionService.collect()` rather than at module top level.

**Review:** Correct approach for breaking the circular import chain. The import-inside-function pattern is established Python practice for this case. The test patching requirement (patch at the defining module, not the service module) is correctly documented.

**Verdict:** Accepted.

### ADR-08-04: Deferrable Checkpoint Constraint

**Decision:** `uq_usage_checkpoints_org_provider_connection` is `DEFERRABLE INITIALLY DEFERRED`.

**Review:** Correct. The checkpoint upsert occurs within a transaction that also writes the collection run and usage events. Without deferral, the constraint could fire mid-transaction before the conflict is resolved by the ON CONFLICT clause.

**Verdict:** Accepted.

### ADR-08-05: BackgroundCollectionFramework — In-Memory Only

**Decision:** Task state is stored in memory; resets on restart.

**Review:** Acceptable for EP-08. The persistent audit trail is the `UsageCollectionRun` record, not the in-memory task record. EP-09 should consider whether a process-restart scenario requires recovery of in-flight tasks (it currently does not — tasks would need to be re-submitted).

**Verdict:** Accepted for EP-08.

---

## Scorecard

| Category | Score | Notes |
|----------|-------|-------|
| Data Model Design | 8/10 | Clean, normalized schema; minor enum name mismatch |
| Pipeline Architecture | 9/10 | Provider-agnostic, idempotent, incrementally checkpointed |
| Error Handling | 6/10 | Silent Anthropic failure; production code with test import |
| API Design | 6/10 | Stubs return misleading 200; no auth enforcement |
| Observability | 8/10 | Structured logging throughout; Anthropic gap |
| Test Coverage | 8/10 | 86 tests; all core paths covered |
| Code Quality | 7/10 | Dead import; lazy imports documented but unusual |
| **Overall** | **7.5/10** | |

---

## Required Changes Before EP-09 Production Deployment

All findings resolved in the EP-08 Release Hardening Sprint (2026-06-29).

| ID | Severity | Action | Status |
|----|----------|--------|--------|
| REV-01 | HIGH | Remove `from unittest.mock import MagicMock` from `app/api/v1/usage.py` | ✅ RESOLVED |
| REV-02 | HIGH | Add `log.warning(...)` to Anthropic `get_usage()` exception handler | ✅ RESOLVED |
| REV-03 | MEDIUM | Return HTTP 501 from stub GET endpoints | ✅ RESOLVED |
| REV-04 | MEDIUM | Align migration enum names with ORM-declared names | ✅ RESOLVED |
| REV-05 | LOW | Document EP-09 deferred persistence in `_run_collection_sync` | ✅ RESOLVED |

REV-01 and REV-02 must be resolved before EP-09 begins. REV-03 and REV-04 may be resolved in the first EP-09 iteration.

---

## EP-09 Prerequisites

The following items are explicitly deferred from EP-08 and must be addressed by EP-09:

1. **AppContainer DB session injection** — replace `_run_collection_sync` with `UsageCollectionService.collect()` using a real session
2. **JWT authentication** — derive `organization_id` from access token claims; reject requests without a valid JWT
3. **GET endpoint implementation** — implement DB-backed query endpoints using `UsageEventRepository`, `UsageCollectionRunRepository`, `UsageCollectionCheckpointRepository`
4. **Provider connection management** — `provider_connection_id` is nullable throughout; EP-09 should define the FK relationship
5. **Scheduler integration** — `BackgroundCollectionFramework.submit()` is available; EP-09 adds the scheduler that calls it on a schedule
6. **`ProviderUsageSummary` population** — the model and repository exist; no code currently calls `upsert_summary()`
