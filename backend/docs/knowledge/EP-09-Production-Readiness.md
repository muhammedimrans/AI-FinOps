# EP-09 Production Readiness Assessment — Cost & Analytics Engine

**Date:** 2026-06-29
**Assessors:** Principal Platform Engineer / Principal Security Engineer / Staff SRE
**Subject:** EP-09 Cost & Analytics Engine (F-050–F-057)
**Branch:** `claude/ai-finops-ep-01-s4d42x`

---

## Summary

EP-09 is **production-ready for development and staging environments** where:
- No real billing decisions are being made from the analytics data
- The cost pipeline is understood to be empty (no `UsageCostRecord` data until EP-10 wires the PricingEngine)
- Operators understand that `organization_id` is not verified against the authenticated user's org membership

EP-09 is **NOT production-ready** for the following reasons:
1. `UsageCostRecord` table is empty — the pricing engine is not wired into the usage collection pipeline (deferred to EP-10)
2. No org membership verification — any authenticated user can query any organization's cost data by supplying an `organization_id` query parameter
3. No RBAC enforcement — `BILLING_READ`, `BILLING_WRITE`, `USAGE_READ` permissions are not checked
4. The `GET /pricing/providers` endpoint silently ignores its `organization_id` parameter

These are the same class of auth gaps that existed in EP-08 and are documented as EP-10 prerequisites.

The financial accuracy, reliability, and data model quality of EP-09 are production-grade. The security and RBAC gaps make it unfit for production until EP-10 closes them.

---

## 1. Financial Accuracy Assessment

### PASS — Decimal Arithmetic

All cost calculations in `PricingEngine.calculate_cost()` use `decimal.Decimal` exclusively. No floating-point operations appear anywhere in the cost calculation path. Price-per-token values are stored as `NUMERIC(20, 10)` and read back as `Decimal` by SQLAlchemy's type system. The intermediate multiplication `Decimal(int_tokens) * Decimal_price` never converts through `float`.

Verification: `test_calculate_cost_returns_decimal_not_float` asserts `isinstance(result["prompt_cost"], Decimal)`.

**Verdict: PASS**

### PASS — Rounding Strategy

`ROUND_HALF_UP` is applied at 8 decimal places using the `_QUANT = Decimal("0.00000001")` quantizer. This is the financial industry standard (0.5 rounds away from zero). Python's default `ROUND_HALF_EVEN` would be non-intuitive for billing amounts.

Each cost component (prompt, completion, cached) is rounded individually before summing, and the total is also quantized. This prevents the accumulation of sub-quantization remainders across many line items.

Verification: `test_calculate_cost_round_half_up` verifies 3 × 0.0000001 = 0.00000030 (not rounded to 0.00000029).

**Verdict: PASS**

### PASS — Historical Pricing Lookup

`ModelPricingRepository.get_for_date()` correctly resolves the pricing version effective on a given date:
- Inclusive on both ends: `effective_from <= date AND effective_to >= date`
- Open-ended support: `effective_to IS NULL` matches any date on or after `effective_from`
- Filters soft-deleted and administratively disabled records
- `ORDER BY effective_from DESC LIMIT 1` ensures deterministic resolution if overlapping records exist

**Verdict: PASS**

### PASS — Currency Handling

Currency is stored on `ModelPricing` and propagated to `UsageCostRecord` at calculation time. Analytics queries that aggregate across records group by `currency` where applicable (provider, model, project, and daily trend breakdowns all group by currency). The one gap (cost summary endpoint aggregating across currencies — see REV-02 in Architecture Review) exists but does not affect correctness in single-currency deployments.

**Verdict: PASS (with caveat for multi-currency — see REV-02)**

### PASS — Cost Reproducibility

Given the same `(pricing_record, prompt_tokens, completion_tokens, cached_tokens)` inputs, `calculate_cost()` always produces the same outputs. The function is pure with no randomness, timestamp dependency, or external state.

`calculation_version` stored on each record enables future detection of records that need repricing if the algorithm changes.

**Verdict: PASS**

### PASS — Deterministic Calculations

The pricing engine is stateless. No caching, no mutable state, no time-dependent calculations (the `usage_date` parameter is provided by the caller — the engine does not call `date.today()` internally). Repeated calls with identical inputs produce identical outputs.

**Verdict: PASS**

---

## 2. Security Assessment

### SEC-01 — Authentication on Pricing Endpoints: PASS

All four pricing endpoints (`POST /calculate`, `GET /models`, `GET /providers`, `POST /models`) require a valid JWT via the `CurrentUser` dependency. Unauthenticated requests return HTTP 401. Verified by tests: `test_calculate_price_requires_auth`, `test_list_model_pricing_requires_auth`, `test_list_pricing_providers_requires_auth`, `test_create_model_pricing_requires_auth`.

**Verdict: PASS**

### SEC-02 — Authentication on Analytics Endpoints: PASS

All six analytics endpoints require JWT via `CurrentUser`. Unauthenticated requests return HTTP 401. Verified by tests: all six `test_*_requires_auth` tests in `TestAnalyticsAPI`.

**Verdict: PASS**

### SEC-03 — Multi-Tenant Isolation: FAIL

`organization_id` is accepted as a query parameter or URL path segment. There is no verification that the authenticated user is a member of the requested organization. Any authenticated user with a valid JWT can supply any `organization_id` and receive that organization's cost data.

This is the same gap that existed in EP-08 (SEC-03 in EP-08 Production Readiness). It is documented throughout the EP-09 codebase as "org membership verification is deferred to EP-10."

**Risk:** In a multi-tenant deployment, this allows horizontal privilege escalation between organizations.

**Verdict: FAIL — blocks production promotion**

### SEC-04 — RBAC Enforcement: FAIL

No RBAC permissions (`BILLING_READ`, `BILLING_WRITE`, `USAGE_READ`) are enforced. Any authenticated user, regardless of role, can:
- Read any organization's cost and usage data
- Create pricing records (which should be admin-only)
- Calculate costs on demand

**Risk:** Users with read-only roles can create pricing configurations, potentially affecting cost calculations for the entire organization.

**Verdict: FAIL — blocks production promotion**

### SEC-05 — Financial Data Protection: PARTIAL

Cost and usage data is stored in standard PostgreSQL tables with no field-level encryption. Row-level security (RLS) is not implemented. Access control is entirely at the application layer.

In development and staging environments where all users are trusted operators, this is acceptable. In production with real customer cost data, additional controls (RLS, column encryption for PII, audit logging of data access) should be evaluated.

**Verdict: PARTIAL — acceptable for dev/staging; evaluate for production**

### SEC-06 — Input Validation: PASS

Request body validation is performed by Pydantic schemas (`ModelPricingCreate`) with `Field(ge=0)` constraints on all price fields. The `PricingValidator` provides an additional application-layer validation. The `effective_to` date is validated against `effective_from` in both the Pydantic schema (via `@field_validator`) and the `PricingValidator`. All database writes use SQLAlchemy parameterized queries — no SQL injection vectors.

**Verdict: PASS**

### SEC-07 — Injection Safety: PASS

All repository methods use SQLAlchemy ORM constructs (`where()`, `and_()`, parameterized values). No raw SQL string interpolation. The `pg_insert().values(**values_dict)` pattern in upsert operations passes values as parameters, not strings. JSONB values are not used in EP-09.

**Verdict: PASS**

---

## 3. Reliability Assessment

### REL-01 — Idempotent Cost Calculation: PASS

`UsageCostRecordRepository.upsert()` uses `ON CONFLICT (uq_usage_cost_records_event) DO UPDATE`. Calling the pricing engine for the same `usage_event_id` multiple times is safe — subsequent calls overwrite all cost fields. No duplicate records are created.

**Verdict: PASS**

### REL-02 — Pricing Not Found Handling: PASS

`PricingEngine.get_pricing_for_event()` raises `PricingNotFoundError` when no pricing record is found. This exception is:
- Logged at WARNING level (not silently swallowed)
- Caught by the API handler and converted to HTTP 404
- Not swallowed anywhere in the pricing engine

When the pricing engine is wired into the collection pipeline (EP-10), the pipeline must handle `PricingNotFoundError` by flagging the event for later repricing rather than failing the entire collection run.

**Verdict: PASS**

### REL-03 — Zero Token Handling: PASS

`PricingEngine.calculate_cost()` with `prompt_tokens=0, completion_tokens=0` correctly returns `Decimal("0.00000000")` for all cost fields. No division-by-zero errors occur. Verified by `test_calculate_cost_zero_tokens`.

**Verdict: PASS**

### REL-04 — Aggregation Correctness: PASS

`AggregationService.build_daily_summaries()` uses `func.coalesce()` around all SUM operations to handle the case where no records exist for a given dimension combination. The result is `0` or `Decimal(0)`, not NULL. The function correctly handles empty result sets (returns `[]` when no records match the org + date filter).

**Verdict: PASS**

### REL-05 — Transaction Safety: PASS

`UsageCostRecordRepository.upsert()` calls `await self._session.flush()` after the `ON CONFLICT` statement. This makes the write visible within the current transaction but does not commit. The session lifecycle is managed by `get_db()` in `app/api/deps.py`, which commits on success and rolls back on exception. All pricing and analytics writes are within a single request/session scope.

**Verdict: PASS**

---

## 4. Scalability Assessment

### SCA-01 — Per-Event Cost Calculation (No Batch in EP-09)

The `PricingEngine.calculate_event_cost()` API is designed for per-event calculation. When wired into the collection pipeline (EP-10), it will be called once per `UsageEvent`. At scale, this means one pricing lookup + one cost record upsert per event. The pricing lookup uses the indexed `get_for_date()` query, which should be O(log n) on the index. The upsert is O(1) with the unique constraint.

For high-throughput scenarios (thousands of events per second), the EP-10 implementation should consider batching the pricing lookups and upserts. The current per-event API is correct but may need a batch variant.

**Assessment: Adequate for current scale; batch variant needed for high throughput**

### SCA-02 — Pre-Aggregated Daily Summaries

`DailyCostSummary` provides O(1) lookup (index scan on `ix_daily_cost_summaries_org_date`) for dashboard queries. At 10 providers × 5 models × 365 days = 18,250 rows per organization per year, the summary table remains small even at scale.

**Assessment: Excellent scalability for read analytics**

### SCA-03 — Index Coverage for Common Query Patterns

All common analytics query patterns are covered by composite indexes:

| Query Pattern | Supporting Index |
|---------------|-----------------|
| Org + date range | `ix_usage_cost_records_org_date` on `(organization_id, usage_date)` |
| Org + provider + date | `ix_usage_cost_records_org_provider_date` |
| Org + project + date | `ix_usage_cost_records_org_project_date` |
| Org + model + date | `ix_usage_cost_records_org_model_date` |
| Pricing lookup | `ix_model_pricing_provider_model_date` on `(provider, model, effective_from)` |

**Assessment: Good index coverage for all defined query patterns**

### SCA-04 — Analytics Query Performance at Scale

Current analytics queries scan `usage_cost_records` with `WHERE organization_id = X AND usage_date BETWEEN A AND B` followed by GROUP BY. With millions of events per organization, these queries may become slow even with the composite index.

The `daily_cost_summaries` table is the long-term solution: a nightly aggregation job (EP-10) keeps it current, and analytics endpoints can read from it instead of `usage_cost_records`. The EP-09 API layer is designed to read from `usage_cost_records` now, with EP-10 able to transparently switch to `daily_cost_summaries` without changing the API contract.

**Assessment: Acceptable for current scale; EP-10 aggregation job is required for production scale**

---

## 5. Performance Assessment

### PERF-01 — Aggregation Queries

The five aggregation queries in `UsageCostRecordRepository` all follow the same pattern:
- `WHERE organization_id = X AND usage_date BETWEEN A AND B AND deleted_at IS NULL`
- `GROUP BY` on the relevant dimension columns
- `ORDER BY SUM(total_cost) DESC`

These queries will use `ix_usage_cost_records_org_date` for the filter phase and perform a hash or sort aggregation. For date ranges of 30 days at 1,000 events/day = 30,000 rows, this is fast. For date ranges of 365 days at 100,000 events/day = 36.5 million rows, this would be slow without the `daily_cost_summaries` table.

**Assessment: PERF-01 is acceptable for dev/staging; production requires the EP-10 aggregation job**

### PERF-02 — Daily Summary Table as Read Optimization

The `daily_cost_summaries` table has 5 indexes covering all analytics access patterns. Once the aggregation job is scheduled, analytics queries can be redirected to `daily_cost_summaries` for orders-of-magnitude better read performance.

**Assessment: Architecture is correct; EP-10 must wire the aggregation job**

### PERF-03 — Missing Indexes

No missing indexes were identified for the currently defined query patterns. The `ix_usage_cost_records_pricing_id` index on `model_pricing_id` supports repricing queries that need to find all records computed under a specific pricing version.

One potential gap: there is no index on `(usage_date)` alone on `usage_cost_records` (only composite indexes including `organization_id`). If a platform-level query (all organizations for a given date) is added in the future, this would require a new index. This is not a current gap.

**Assessment: PASS for current query patterns**

---

## 6. Observability Assessment

### OBS-01 — Structured Logging: PASS

All EP-09 modules use `structlog.get_logger(__name__)`. Log calls include relevant context in keyword arguments:
- `PricingEngine`: `pricing_not_found` (WARNING) and `pricing_resolved` (DEBUG)
- `AggregationService`: `building_daily_summaries` (INFO), `daily_summaries_built` (INFO), `rebuilding_summary_range` (INFO), `summary_range_rebuilt` (INFO)
- `UsageCostRecordRepository`: `upsert_cost_record_not_found` (WARNING) for the edge case where the post-upsert SELECT returns None
- API handlers: `pricing_created` (INFO)

No `print()` statements in any EP-09 code.

**Verdict: PASS**

### OBS-02 — Pricing Calculation Audit Trail: PASS

Every `UsageCostRecord` stores:
- `model_pricing_id` — the specific pricing version used
- `calculation_version` — the algorithm version used
- `updated_at` — when the cost was last calculated (updated on every upsert)

This provides a complete audit trail: given any cost record, an operator can determine exactly what pricing was applied and when the calculation was performed.

**Verdict: PASS**

### OBS-03 — Missing Metrics: PARTIAL

No Prometheus metrics, StatsD counters, or OpenTelemetry spans are emitted from EP-09 code. There is no metric for:
- Number of pricing calculations per unit time
- Number of `PricingNotFoundError` events (cost records that could not be priced)
- Aggregation job duration (once wired in EP-10)
- Total cost computed per organization per day

The structured logging provides a substrate for log-based metrics, but dedicated metrics instrumentation would be preferred for production monitoring.

**Verdict: PARTIAL — acceptable for dev/staging; metrics instrumentation recommended before production**

---

## 7. Deployment Assessment

### DEP-01 — Alembic Migration Correctness: PASS

Migration `f7a8b9c0d1e2` has been reviewed in detail:
- Creates tables in FK-dependency order: `model_pricing` → `usage_cost_records` → `daily_cost_summaries`
- All constraint names match ORM model definitions
- All precision types match (`NUMERIC(20,10)` and `NUMERIC(20,8)`)
- Downgrade reverses in strict reverse order
- No irreversible data changes (all three tables are new in EP-09)
- No lock-heavy operations (no ALTER TABLE on existing large tables)
- Revises `e6f7a8b9c0d1` (EP-08 migration) — the chain is correct

**Verdict: PASS**

### DEP-02 — External Dependencies: PASS

EP-09 introduces no new external dependencies. All packages used (`sqlalchemy`, `pydantic`, `structlog`, `fastapi`, `decimal` from stdlib) were already present. No new pip packages, no new environment variables, no new infrastructure services.

**Verdict: PASS**

### DEP-03 — Rollback Safety: PASS

The migration downgrade is safe because:
- All three new tables are dropped in reverse dependency order
- No existing tables are modified
- No data migrations are required for rollback
- Downgrade restores the database to the exact EP-08 state

In the event of a rollback, the application code must also be reverted to EP-08 (the Python code for the new packages and API endpoints must be removed). A partial state (migration applied but code reverted or vice versa) would cause startup errors, which is the correct behavior — it prevents partial functionality.

**Verdict: PASS**

---

## 8. API Readiness Assessment

### API-01 — Pricing Trigger Endpoints: PARTIAL

`POST /v1/pricing/calculate` is functional — it resolves pricing and returns accurate costs. However, the endpoint is primarily useful for testing pricing configurations in EP-09. It will not be exercised in production until the pricing engine is wired into the collection pipeline (EP-10).

`POST /v1/pricing/models` allows creation of pricing records. This is functional and can be used in production to configure pricing before EP-10 wires the calculation pipeline.

**Verdict: PARTIAL — functional but not exercised end-to-end until EP-10**

### API-02 — Analytics Query Endpoints: PARTIAL

All six analytics endpoints are functional and return correct responses when `usage_cost_records` contains data. However, `usage_cost_records` will be empty until EP-10 wires the pricing engine into the collection pipeline. Until then, all analytics endpoints will return zero totals and empty arrays.

**Verdict: PARTIAL — correct logic but returns zero data until EP-10**

### API-03 — OpenAPI Schema: PASS

All endpoints have `summary` and `description` parameters documenting their behavior. Response models are typed Pydantic schemas. FastAPI generates a complete OpenAPI schema from these definitions. The Decimal-as-string convention is reflected in the schema (`str` type for monetary fields).

**Verdict: PASS**

### API-04 — Request Validation: PASS

All request bodies use typed Pydantic models with field-level validators:
- `ModelPricingCreate`: `Field(..., ge=0)` on all price fields; `@field_validator` on `effective_to`
- `PriceCalculationRequest`: `Field(..., ge=0)` on all token fields
- Date parameters: parsed as `date` type by FastAPI/Pydantic; invalid dates return HTTP 422

**Verdict: PASS**

---

## 9. Production Risk Register

| ID | Severity | Risk | Impact | Mitigation |
|----|----------|------|--------|------------|
| PRR-01 | HIGH | No org membership verification — any authenticated user can access any org's cost data | Horizontal privilege escalation in multi-tenant deployment | MUST BE RESOLVED in EP-10 before production |
| PRR-02 | HIGH | No RBAC on pricing write endpoints — any authenticated user can create pricing records | Pricing misconfiguration by non-admin users affecting all cost calculations | MUST BE RESOLVED in EP-10 before production |
| PRR-03 | HIGH | `usage_cost_records` is empty — all analytics return zero | No observable value from analytics endpoints until EP-10 wires the pipeline | Known EP-09 stop condition; resolve in EP-10 |
| PRR-04 | MEDIUM | `GET /pricing/providers` ignores `organization_id` — returns all platform providers | Users see providers they shouldn't know about | Low impact in single-tenant mode; fix in EP-10 |
| PRR-05 | MEDIUM | Multi-currency cost summary aggregates across currencies | Incorrect total costs in multi-currency deployments | Not currently triggered (USD-only); fix before enabling multi-currency pricing |
| PRR-06 | MEDIUM | No aggregation job scheduled — `daily_cost_summaries` not populated | Analytics queries scan `usage_cost_records` directly — performance degrades at scale | Schedule aggregation job in EP-10 |
| PRR-07 | LOW | No Prometheus/OpenTelemetry metrics on pricing calculations | Reduced operational visibility into cost calculation health | Add metrics in EP-10 or later |
| PRR-08 | LOW | Cursor pagination not propagated in filtered pricing list path | API clients cannot page through provider-specific pricing lists | Fix in EP-10 before building admin UI |
| PRR-09 | LOW | `get_top_models`/`get_top_projects` fetch all results and slice in Python | Performance degradation if organization uses many models | Add LIMIT to SQL queries in EP-10 |
| PRR-10 | LOW | Import inside for loop in `AggregationService` | No runtime impact (Python caches imports); code style concern | Fix in EP-10 housekeeping |

---

## 10. EP-09.5 Gap Analysis

| ID | Blocking | Item | Owner |
|----|----------|------|-------|
| G-01 | YES | Org membership verification on all analytics and pricing endpoints | EP-10 Auth |
| G-02 | YES | RBAC enforcement: `BILLING_READ`, `BILLING_WRITE`, `USAGE_READ` | EP-10 Auth |
| G-03 | YES | Wire `PricingEngine.calculate_event_cost()` into `UsageCollectionService.collect()` | EP-10 Collection Pipeline |
| G-04 | YES | Derive `organization_id` from JWT claims rather than query parameter | EP-10 Auth |
| G-05 | NO | Resolve `GET /pricing/providers` ignoring `organization_id` (REV-05) | EP-10 Housekeeping |
| G-06 | NO | Fix multi-currency aggregation in `get_totals_by_org()` (REV-02) | EP-10 Housekeeping |
| G-07 | NO | Schedule `AggregationService.rebuild_range()` as nightly cron job | EP-10 Scheduling |
| G-08 | NO | Pricing cascade recalculation on pricing record update | EP-10 Repricing |
| G-09 | NO | Propagate cursor in filtered `/pricing/models` path (REV-01) | EP-10 API |
| G-10 | NO | Add Prometheus/OpenTelemetry metrics for pricing calculations | EP-10 Observability |
| G-11 | NO | Add LIMIT parameter to `get_top_models`/`get_top_projects` SQL queries (REV-07) | EP-10 Housekeeping |
| G-12 | NO | Move import inside loop in `AggregationService` to module top level (REV-06) | EP-10 Housekeeping |

Items G-01 through G-04 are blocking: EP-10 cannot be deployed to production without them.

---

## Final Verdict

**EP-09 is APPROVED for development and staging environments.**

**EP-09 is NOT approved for production** pending resolution of G-01 through G-04:
- G-01: Org membership verification
- G-02: RBAC enforcement
- G-03: PricingEngine wiring into collection pipeline
- G-04: JWT org binding

The financial accuracy and reliability of the cost calculation engine are production-grade. The security gaps are known, documented, and fully addressable in EP-10. No findings require changes to the EP-09 code before EP-10 begins — all blocking items are new work in EP-10.

EP-09 may be merged and deployed to development and staging immediately.
