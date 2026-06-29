# EP-08 Production Readiness Assessment — Usage Collection Engine

**Date:** 2026-06-29  
**Assessors:** Principal Platform Engineer / Principal Security Engineer / Staff SRE  
**Subject:** EP-08 Usage Collection Engine (F-041–F-049)

---

## Summary (Updated post-hardening 2026-06-29)

Items REV-01 and REV-02 have been resolved in the EP-08 Release Hardening Sprint. REV-05 is formally documented as an EP-08 stop condition.

EP-08 is **NOT production-ready** for the following remaining reasons:
1. POST `/collect` endpoints return success responses while persisting nothing to DB (deferred to EP-09)
2. No JWT authentication on any usage endpoint (deferred to EP-09)

EP-08 IS production-ready for **development and staging** environments. EP-09 must resolve items G-03 and G-04 before any production promotion.

EP-08 IS production-ready for **development and staging** environments where:
- No real usage data is being collected for billing purposes
- The limitations above are acceptable for integration testing
- Operators have direct DB access for debugging

This assessment documents the risk register, gap analysis, and prerequisites for production promotion.

---

## 1. Security Assessment

### SEC-01 — Credential Handling: PASS

API keys are resolved via `SecretResolver` from environment variables. The secret value is:
- Held in memory only for the duration of a single adapter method call
- Never written to logs (structlog context does not include credential values)
- Never included in error messages (`AuthenticationError` contains the provider name, not the key)
- Never serialized to JSON or stored in the database

The `SecretStr` Pydantic type masks key values in repr and JSON serialization.

**Verdict:** No credential leakage risk identified.

### SEC-02 — SSRF Protection: PASS (inherited from EP-06.5)

SSRF protection is implemented at the `ProviderConfig` layer (EP-06.5 REC-02). All provider `base_url` / `azure_endpoint` values are validated at config construction. Cloud-metadata hosts, loopback addresses, private IPs, and non-HTTP/S schemes are blocked.

EP-08 does not introduce new URL construction paths. The `get_usage()` calls use the provider's pre-configured and already-SSRF-checked base URL.

**Verdict:** No new SSRF attack surface introduced.

### SEC-03 — Multi-Tenant Isolation: PARTIAL

`organization_id` is accepted as a query parameter / request body field. There is no enforcement that the caller is authorized to access data for the provided `organization_id`.

- Any caller with network access can supply any `organization_id`
- Collection triggers run against the single configured API key regardless of `organization_id`
- Query endpoints (stubs) do not enforce isolation because they return no data

In development/staging this is acceptable. In production, `organization_id` MUST be derived from the authenticated JWT claims, not accepted from the request body.

**Verdict:** Partial pass for development; FAIL for production until JWT authentication is implemented.

### SEC-04 — No Authentication on Collection Endpoints: FAIL for Production

`POST /v1/usage/collect` and `POST /v1/usage/collect/{provider}` have no authentication mechanism. Any caller can trigger a usage collection run against the configured provider API keys.

Risks:
- Credential abuse: an attacker can trigger repeated collection runs, causing rate-limit exhaustion on the provider API keys
- Denial of service: concurrent collection runs against the semaphore-limited framework
- Cost amplification: if EP-09 adds cost calculations, unauthenticated triggers could flood the cost pipeline

**Verdict:** FAIL — authentication must be added before production deployment.

### SEC-05 — Raw Provider Payload Storage: ACCEPTABLE

`raw_provider_payload` (JSONB) stores the full original API response item. Provider API responses for usage data do not typically contain secrets or PII. However:
- If Anthropic includes user-identifiable request metadata in future API versions, this field would capture it
- No field-level encryption or masking is applied

**Verdict:** Acceptable for current providers. Monitor Anthropic API response schema for PII additions.

### SEC-06 — Injection Safety: PASS

All database writes use SQLAlchemy parameterized queries. No string interpolation into SQL. JSONB values are passed as Python dicts, not raw strings.

**Verdict:** No SQL injection risk identified.

---

## 2. Reliability Assessment

### REL-01 — Idempotent Collection Runs: PASS

All persistence paths use ON CONFLICT DO UPDATE. Re-running the same date range produces the same result. Safe to retry failed runs.

### REL-02 — Incremental Checkpointing: PASS

Checkpoint is updated after every page. Interrupted runs lose at most one page of events. Subsequent runs resume from the last checkpoint position.

### REL-03 — Per-Provider Failure Isolation: PASS

`collect_all` catches per-provider exceptions and continues collecting from other providers. A single provider failure does not abort the full collection pass.

### REL-04 — Anthropic Silent Failure: FAIL

The Anthropic adapter catches all exceptions and returns an empty `UsagePage` with no log output. This makes the following failure modes indistinguishable:
- Expected: account does not have Anthropic admin usage API access
- Unexpected: network failure to Anthropic API
- Unexpected: API key revoked or rate-limited
- Unexpected: bug in the normalization path

**Risk:** A real data loss event (e.g., API key revoked mid-month) would be reported as `events_collected=0` with status `COMPLETED`, identical to a month with no activity. An operator would not know to investigate.

**Resolution:** Log the exception at WARNING before returning (see REV-02 in Architecture Review).

### REL-05 — Background Task State Lost on Restart: ACCEPTABLE

`BackgroundCollectionFramework` stores task state in memory. On process restart, all in-progress tasks are lost. The `UsageCollectionRun` record persists the result if the task completed before restart; in-flight tasks are abandoned with no cleanup.

For EP-08 (manually triggered, no production traffic), this is acceptable. EP-09 must address:
- Recovery of in-flight runs after restart (mark stale RUNNING runs as FAILED)
- Scheduled trigger persistence (so scheduled tasks are not lost on restart)

### REL-06 — Collection Run Marked FAILED Before Session Commit: ACCEPTABLE

`UsageCollectionService.collect()` raises after marking the run FAILED. The caller (API or background framework) receives the exception. The session is NOT automatically committed on failure — the caller must commit. If the caller does not commit, the FAILED status is lost.

The background framework uses `async with session.begin()`, which commits on success and rolls back on exception. If the service marks the run FAILED and re-raises, the transaction rolls back — meaning the FAILED run record is also lost.

**Risk:** Failed collection runs may not appear in the database, making failure debugging impossible.

**Resolution for EP-09:** The run status update should be committed in a separate transaction from the event upserts, or the FAILED status should be written outside the main transaction scope.

---

## 3. Scalability Assessment

### SCA-01 — Concurrent Collection Semaphore: PASS

`BackgroundCollectionFramework` uses `asyncio.Semaphore(max_concurrent)` to limit concurrent collection tasks. Default is 5. This prevents runaway task creation from exhausting event loop capacity.

### SCA-02 — Page Size Limit: PASS

`UsageCollectionService` uses `page_limit=100` (configurable at construction). This bounds memory usage per collection iteration.

### SCA-03 — In-Memory Task Registry Growth: ACCEPTABLE

`_tasks: dict[uuid.UUID, CollectionTaskRecord]` grows indefinitely — completed tasks are never evicted. For EP-08 with manual triggers, this is negligible. For EP-09 with scheduled triggers (e.g., hourly collection for 10 providers = 240 records/day), the dict will grow large over time.

**Resolution for EP-09:** Implement a TTL-based eviction policy for completed/failed/cancelled tasks.

### SCA-04 — Single-Process Background Framework: ACCEPTABLE for EP-08

The background framework is process-local. In a multi-process deployment (e.g., multiple uvicorn workers), each worker has its own framework instance with its own task dict. A task submitted to worker 1 cannot be queried from worker 2.

This is acceptable for EP-08 where collection is triggered manually and results are persisted to the database. EP-09's scheduler should run in a single dedicated process (not the API process pool) to avoid this multi-process issue.

---

## 4. Performance Assessment

### PERF-01 — No Connection Pool Sharing in get_usage(): KNOWN GAP (inherited)

The EP-07.5 finding ARC-01 (connection pool churn) applies to the `get_usage()` adapter implementations. Each call to `adapter.get_usage()` creates a new `httpx.AsyncClient` and closes it at the end of the call. For multi-page collection, this creates N client instances where N is the page count.

EP-07.5 resolved this for `verify_auth()` / `check_connection()`. EP-08 extended the same pattern to `get_usage()`. The fix (share a single `ProviderHttpClient` across method calls) should be applied to `get_usage()` in EP-09.

### PERF-02 — Per-Event Upsert (No Batch): LOW RISK for EP-08

`UsageCollectionService._process_page()` calls `event_repo.upsert(orm_event)` once per event in a loop. For a page of 100 events, this is 100 separate INSERT statements.

For EP-08 usage volumes (typically hundreds of events per day per provider), this is acceptable. For EP-09 at scale (millions of events per day), a batch upsert should be implemented.

### PERF-03 — Synchronous Collection Endpoint Blocks Event Loop: MEDIUM RISK

`POST /v1/usage/collect` is a FastAPI async endpoint that runs `adapter.get_usage()` inline. If the provider API is slow (e.g., 30-second response time), the endpoint handler is blocked for 30 seconds while holding an event loop slot. This reduces the server's ability to handle concurrent requests.

**Resolution for EP-09:** Use `BackgroundCollectionFramework.submit()` for the trigger endpoints and return the task_id immediately (true 202 Accepted pattern).

---

## 5. Observability Assessment

### OBS-01 — Structured Logging: PASS

All log calls use `structlog` with bound context. Key structured fields:
- `organization_id` — on every collection log
- `provider` — on every collection log
- `run_id` — bound after run creation
- `page` / `events_created` / `events_failed` — per-page metrics
- Background task: `task_id` on every task lifecycle event

### OBS-02 — Collection Run as Audit Trail: PASS

Every collection pass creates a `UsageCollectionRun` record with start/end timestamps, event counts, page counts, and error messages. This provides a queryable audit trail (once the GET endpoints are implemented in EP-09).

### OBS-03 — Anthropic Failure Observability: FAIL

The Anthropic silent failure (REV-02) means Anthropic collection failures produce no log output and no differentiating signal in the collection run record (`events_collected=0` is indistinguishable from a normal empty period).

### OBS-04 — No Metrics / Telemetry: ACCEPTABLE for EP-08

No Prometheus metrics, Datadog metrics, or OpenTelemetry traces are emitted. EP-08 relies entirely on log aggregation for observability. For EP-09 production deployment, metrics should be added:
- `usage_events_collected_total` (counter, by provider)
- `usage_collection_duration_seconds` (histogram, by provider)
- `usage_collection_failures_total` (counter, by provider, error_type)

### OBS-05 — No Health Endpoint for Collection Subsystem: ACCEPTABLE for EP-08

The existing `GET /v1/health` endpoint does not include collection subsystem health. EP-09 should add collection status to the health check.

---

## 6. Deployment Assessment

### DEP-01 — Alembic Migration: PASS (with caveat)

The Alembic migration `e6f7a8b9c0d1` creates all 4 tables with correct indexes and constraints. The migration can be applied and rolled back.

**Caveat:** Enum type name mismatch (REV-04 in Architecture Review). The migration creates `collectionrunstatus` / `collectiontrigger` while the ORM declares `collection_run_status` / `collection_trigger`. This works at runtime but will cause confusion for future migrations.

### DEP-02 — No External Dependencies Added: PASS

EP-08 uses only dependencies already present:
- `sqlalchemy` + `asyncpg` — already a requirement
- `structlog` — already a requirement
- `pydantic` v2 — already a requirement
- `httpx` (via ProviderHttpClient) — already a requirement
- `hashlib` — Python standard library

No new packages were added to `requirements.txt` or `pyproject.toml`.

### DEP-03 — Environment Variables: PASS

EP-08 requires no new environment variables. `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` were added in EP-07. The usage collection system reads from the same env vars via `SecretResolver`.

### DEP-04 — Database Migration Order: PASS

The migration revises `d5e6f7a8b9c0` (EP-07). Tables are created in dependency order. Downgrade drops tables in reverse order.

---

## 7. API Readiness Assessment

### API-01 — Collection Trigger Endpoints: CONDITIONALLY READY

`POST /v1/usage/collect` and `POST /v1/usage/collect/{provider}` are functionally correct but:
- Persist nothing to the database (REV-05)
- Have no authentication
- Block the event loop for the duration of collection

For staging integration testing: ready.  
For production: not ready.

### API-02 — Query Endpoints: NOT READY

Six endpoints are hard stubs. They return empty/404 responses regardless of database state. Not suitable for any use case.

### API-03 — OpenAPI Schema: PASS

All endpoints have correct `response_model` declarations, status codes, summaries, and descriptions. FastAPI generates a correct OpenAPI schema from the endpoint definitions.

### API-04 — Request Validation: PASS

Pydantic v2 validates all request bodies. Invalid `organization_id` (non-UUID) returns HTTP 422. Missing required fields return HTTP 422. Unsupported providers return HTTP 404.

---

## 8. Production Risk Register

| ID | Severity | Risk | Impact | Mitigation |
|----|----------|------|--------|-----------|
| PRR-01 | CRITICAL | No authentication on collection endpoints | Any caller can trigger API key usage | Add JWT authentication before production |
| PRR-02 | HIGH | `unittest.mock` import in production code | Code quality; may fail security scans | ✅ RESOLVED — removed in hardening sprint |
| PRR-03 | HIGH | Anthropic failures fully silent | Data loss not detectable | ✅ RESOLVED — log.warning emitted before fallback |
| PRR-04 | HIGH | Collection does not persist to DB | 200 OK with no data written | EP-09 DB session injection required |
| PRR-05 | MEDIUM | GET endpoints return empty 200 | Misleading API contract | ✅ RESOLVED — stubs return HTTP 501 |
| PRR-06 | MEDIUM | Migration enum name mismatch | Future migration failures | ✅ RESOLVED — names aligned in migration |
| PRR-07 | MEDIUM | In-flight tasks lost on restart | Incomplete collection runs not recoverable | Mark stale RUNNING runs as FAILED on startup |
| PRR-08 | MEDIUM | Per-event upsert (no batch) | Performance at scale | Implement batch upsert for EP-09 |
| PRR-09 | MEDIUM | Connection pool churn in get_usage() | Latency; TCP connection exhaustion | Share ProviderHttpClient across pages |
| PRR-10 | LOW | In-memory task registry grows unbounded | Memory leak in long-running process | TTL eviction for completed tasks |
| PRR-11 | LOW | Checkpoint FAILED status lost on rollback | Debugging incomplete runs | Write FAILED status outside main transaction |

---

## 9. EP-08.5 Gap Analysis

The following items MUST be resolved before EP-09 production traffic is accepted. Items marked BLOCKING may also be resolved within the first EP-09 iteration, but must be complete before any production deployment.

| ID | Blocking | Item | Owner |
|----|----------|------|-------|
| G-01 | YES | Remove `unittest.mock` import from `app/api/v1/usage.py` | EP-08.5 |
| G-02 | YES | Log Anthropic exception before returning empty UsagePage | EP-08.5 |
| G-03 | YES | Add JWT authentication to collection trigger endpoints | EP-09 |
| G-04 | YES | Inject DB session into `_run_collection_sync` (use `UsageCollectionService`) | EP-09 |
| G-05 | YES | Implement GET query endpoints with real DB queries | EP-09 |
| G-06 | NO | Return HTTP 501 from stub endpoints (interim) | EP-08.5 or EP-09 |
| G-07 | NO | Align migration enum type names with ORM-declared names | EP-08.5 |
| G-08 | NO | Mark stale RUNNING runs as FAILED on service startup | EP-09 |
| G-09 | NO | Implement batch upsert for `UsageEventRepository` | EP-09 |
| G-10 | NO | Add `ProviderUsageSummary` population to collection pipeline | EP-09 |
| G-11 | NO | Add prometheus metrics (events_collected, duration, failures) | EP-09 |
| G-12 | NO | TTL eviction for completed tasks in `BackgroundCollectionFramework` | EP-09 |

---

## Final Verdict

**EP-08 is APPROVED WITH MINOR CHANGES for development and staging.**

Items G-01 and G-02 (corresponding to REV-01 and REV-02 in the Architecture Review) must be resolved before EP-09 begins. These are small, targeted fixes that do not require architectural changes.

Items G-03 through G-05 are structural EP-09 prerequisites and must be completed before any production deployment.

All other gap items may be addressed within the EP-09 development cycle, coordinated with the EP-09 architecture design.
