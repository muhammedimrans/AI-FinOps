# EP-09 Architecture Review — Cost & Analytics Engine

**Date:** 2026-06-29
**Reviewers:** Principal Software Architect / Principal FinOps Architect / Staff Database Engineer
**Subject:** EP-09 Cost & Analytics Engine (F-050–F-057)
**Branch:** `claude/ai-finops-ep-01-s4d42x`

---

## Executive Summary

EP-09 delivers a well-designed cost and analytics engine that correctly addresses the core requirements of FinOps: versioned pricing, deterministic cost calculation, cost attribution with multi-dimensional analytics, and pre-aggregated daily summaries for query performance. The use of `decimal.Decimal` throughout the cost calculation stack, the idempotent upsert patterns, and the historical pricing resolution algorithm are all sound.

Seven findings are raised. None are CRITICAL. Two are MEDIUM severity and should be resolved before EP-10 production deployment. Five are LOW severity and may be tracked as EP-10 backlog items. The most significant finding (REV-02) identifies a multi-currency aggregation gap in analytics queries that does not affect correctness in single-currency deployments but would produce incorrect results in a multi-currency environment. REV-01 identifies a missing cursor propagation in the filtered pricing list path, which is a minor API contract gap. REV-05 identifies that `GET /pricing/providers` ignores its required `organization_id` query parameter, which is a tenant isolation gap.

The architecture is sound and the implementation is production-ready for development and staging environments. Auth-related gaps (documented throughout EP-09 code as "deferred to EP-10") must be resolved before production promotion.

**Overall Score: 8.5 / 10**

**Final Decision: APPROVED WITH MINOR CHANGES**

---

## Architecture Score

| Category | Score | Justification |
|----------|-------|---------------|
| Data Model Design | 9/10 | Correct precision types, solid constraint design, clean FK relationships, good index coverage |
| Pricing Engine Architecture | 9/10 | Stateless, deterministic, correct Decimal arithmetic, proper ROUND_HALF_UP, clean error handling |
| Repository Pattern | 9/10 | Consistent upsert pattern, correct ON CONFLICT constraint names, clean aggregation queries |
| Service Layer Design | 8/10 | Clean read/write separation, AnalyticsService correctly read-only; top_models/top_projects in-Python slicing is a minor inefficiency |
| API Design | 7/10 | Good endpoint structure; cursor not propagated in filtered list; providers endpoint ignores org_id |
| Financial Accuracy | 9/10 | Decimal throughout, ROUND_HALF_UP, no float leakage found; multi-currency aggregation gap is a future concern |
| Test Coverage | 9/10 | 135 tests, hermetic, precision verification at Decimal exponent level, auth guards tested |
| Code Quality | 9/10 | Structured logging, no silent exceptions, clean separation, consistent patterns |
| **Overall** | **8.5/10** | Strong foundation; minor gaps documented; ready for EP-10 with tracked findings |

---

## Architecture Strengths

### S-01 — Correct Decimal Arithmetic Throughout

**File:** `app/pricing/engine.py`, lines 96–111

The `PricingEngine.calculate_cost()` method is entirely free of floating-point arithmetic. Every computation uses `Decimal(int_value) * Decimal_price_field`. The quantization `_QUANT = Decimal("0.00000001")` with `rounding=ROUND_HALF_UP` is applied to each component cost individually before summing. This is the correct approach: rounding per-component (not only the final sum) prevents accumulation of sub-cent precision across multiple line items.

The test `test_calculate_cost_precision_8dp` verifies the Decimal exponent directly (`result["prompt_cost"].as_tuple().exponent == -8`), which is a strong assertion — it checks the structure of the Decimal object, not just numeric equality.

### S-02 — Idempotent Upserts on All Write Paths

**Files:** `app/repositories/usage_cost_record_repository.py`, line 69; `app/repositories/daily_cost_summary_repository.py`, line 54

Both upsert operations use PostgreSQL `INSERT ... ON CONFLICT DO UPDATE` with named constraint references. The constraint names used in the `on_conflict_do_update()` calls (`"uq_usage_cost_records_event"` and `"uq_daily_cost_summaries"`) match the constraint names defined in the ORM models and in the Alembic migration — a cross-layer consistency check that is easy to get wrong and was done correctly here.

Re-running cost calculation for the same events is safe: the upsert replaces all cost fields and updates `updated_at` via `func.now()`. This enables the EP-10 repricing workflow to be implemented as a simple recalculate-and-upsert loop.

### S-03 — Historical Pricing Resolution Algorithm

**File:** `app/repositories/model_pricing_repository.py`, lines 40–66

The `get_for_date()` query correctly implements the inclusive date range lookup:
- `effective_from <= usage_date` — correct (not strict less-than)
- `effective_to IS NULL OR effective_to >= usage_date` — correct (inclusive end, NULL = open)
- `ORDER BY effective_from DESC LIMIT 1` — correct tiebreaker (most recently effective wins if overlap was not enforced)
- Filters `is_active = TRUE` and `deleted_at IS NULL` — correct (soft-delete and administrative disable both respected)

The compound index `ix_model_pricing_provider_model_date` on `(provider, model, effective_from)` directly supports the `effective_from <= date` predicate after the equality filters on `provider` and `model`.

### S-04 — Clean Separation of Concerns

The EP-09 architecture maintains three distinct concerns with hard boundaries:

1. **Pricing Engine** (`app/pricing/`) — resolves pricing and calculates costs. Reads only `ModelPricing`. Does not write anything.
2. **Analytics Service** (`app/analytics/service.py`) — reads cost records. Does not calculate costs or modify records.
3. **Aggregation Service** (`app/analytics/aggregation.py`) — reads cost records, writes summaries. Does not calculate costs.

None of these cross-boundary. `AnalyticsService.__init__` accepts only repositories (not the session directly), preventing direct SQL execution from the analytics service.

### S-05 — Provider-Agnostic Design

Provider and model are stored as `VARCHAR` strings throughout (`model_pricing`, `usage_cost_records`, `daily_cost_summaries`). No enum column is used for provider. This means:
- Adding a new provider requires zero schema changes
- Analytics queries work identically across all providers
- Historical pricing for retired providers is preserved indefinitely

This is the correct design for a system that tracks costs across an evolving landscape of AI providers.

### S-06 — Structured Logging with Correct Contexts

**Files:** `app/pricing/engine.py`, `app/analytics/aggregation.py`, `app/repositories/usage_cost_record_repository.py`

All log calls use `structlog.get_logger(__name__)` and include relevant context in keyword arguments (`provider`, `model`, `usage_date`, `pricing_id`, `organization_id`, etc.). The `log.warning("pricing_not_found", ...)` in `PricingEngine.get_pricing_for_event()` provides an observable signal for un-priced models without raising a log-alarming `ERROR` — correctly distinguishing a configuration gap from a system error.

### S-07 — Migration Correctness

**File:** `migrations/versions/20260629_0900_f7a8b9c0d1e2_ep09_cost_analytics.py`

The Alembic migration correctly:
- Uses `NUMERIC(20, 10)` for price-per-token fields and `NUMERIC(20, 8)` for computed costs (matching ORM definitions)
- Creates all 3 unique constraints with names matching the ORM model `__table_args__`
- Creates all 17 indexes matching the ORM model index definitions
- Creates all 7 FK constraints with matching `name=` values
- Drops in strict reverse order: daily_cost_summaries → usage_cost_records → model_pricing

The FK constraint names in the migration match those in the ORM models exactly (e.g., `"fk_usage_cost_records_usage_event_id"`), which is necessary for Alembic autogenerate comparison to produce clean "no changes" output.

### S-08 — Test Coverage for Financial Accuracy

**File:** `tests/test_ep09.py`, `TestPricingEngine` class

The test suite includes specific tests for:
- Zero-token calculation producing `Decimal("0.00000000")` (not an error or division-by-zero)
- Exact precision at 8 decimal places (`as_tuple().exponent == -8`)
- `ROUND_HALF_UP` behavior with a case designed to trigger the rounding boundary
- `isinstance(result["prompt_cost"], Decimal)` — type assertion, not just value assertion
- `PricingNotFoundError` propagation through both `get_pricing_for_event()` and `calculate_event_cost()`

---

## Architecture Findings

### REV-01 — LOW: Cursor Pagination Not Propagated in Filtered List Path

**Severity:** LOW
**Category:** API Design
**File:** `app/api/v1/pricing.py`, lines 128–147

The `GET /v1/pricing/models` endpoint handles three query paths:
1. `provider` + `model` → `list_for_model()` → returns all versions, no pagination
2. `provider` only → `list_for_provider()` → returns all records for provider, no pagination
3. No provider filter → `list_page(limit=limit)` → returns cursor-paginated page

In paths 1 and 2, the `next_cursor` field in the response is always `None`, and `has_more` is computed by checking `len(items) > limit` after truncating to `limit`. This means:
- If a provider has 150 pricing records, the response returns the first `limit` items with `has_more=True` but `next_cursor=None` — a client cannot fetch the next page
- This is a broken pagination contract

**Proposed Resolution:** For filtered paths, either (a) return all records without limit (acceptable for admin endpoints where the count is bounded), or (b) implement cursor pagination on the filtered queries using `list_page(extra_filters=...)`. Option (a) is simpler and sufficient for EP-09.

**Estimated Effort:** 1 hour

---

### REV-02 — MEDIUM: Multi-Currency Aggregation Produces Incorrect Cross-Currency Sums

**Severity:** MEDIUM
**Category:** Financial Accuracy
**File:** `app/repositories/usage_cost_record_repository.py`, `get_totals_by_org()`, lines 98–130

`get_totals_by_org()` returns a single row with `SUM(total_cost)` across all currencies. If an organization uses both USD-priced and EUR-priced models, this aggregation would sum USD and EUR costs into a single number — which is financially incorrect (you cannot add $100 and €100 without a conversion rate).

The other aggregation methods (`get_totals_by_provider`, `get_totals_by_model`, `get_totals_by_project`, `get_daily_trend`) correctly group by `currency`. However, `get_totals_by_org` does not group by currency and returns a single `total_cost` value. The `AnalyticsService.get_cost_summary()` returns this as a single `total_cost` field.

This is not a bug in single-currency deployments (which is the current use case, as all providers default to USD). However, the schema supports multi-currency and the API contract should reflect it.

**Proposed Resolution:** Modify `get_totals_by_org()` to GROUP BY currency and return a list of per-currency totals (matching the pattern of the other aggregation methods). Update `get_cost_summary()` and `CostSummaryResponse` to return `list[dict]` with per-currency breakdown. This is a breaking API change for EP-09 consumers; it should be addressed before EP-10 which may introduce real multi-currency scenarios.

**Estimated Effort:** 3 hours (repository + service + schema + API + tests)

---

### REV-03 — LOW: `get_totals_by_org` Aggregation Query Is Missing Soft-Delete Filter

**Severity:** LOW
**Category:** Data Correctness
**File:** `app/repositories/usage_cost_record_repository.py`, line 113–120

The `get_totals_by_org()` method correctly applies `UsageCostRecord.deleted_at.is_(None)` in its WHERE clause (line 119). However, this filter is manually added to each aggregation method rather than being inherited from `_active_query()`. An audit of all five aggregation methods confirms they all include this filter correctly.

This is NOT a bug — all five methods have the filter. However, the pattern of manually adding the filter is fragile: a future developer adding a sixth aggregation method might omit it. This is a maintainability concern.

**Proposed Resolution:** Consider refactoring the aggregation queries to start from `self._active_query()` (which automatically applies the soft-delete filter) and then add the GROUP BY and aggregate columns. Alternatively, document the requirement explicitly in a comment in the repository class docstring.

**Estimated Effort:** 1 hour

---

### REV-04 — LOW: `PriceCalculationRequest.usage_date` Defaults to `date.today()` Server-Side

**Severity:** LOW
**Category:** API Design
**File:** `app/api/v1/pricing.py`, line 70

```python
usage_date = body.usage_date or date.today()
```

`date.today()` returns the server's local date. If the API server is in UTC and a client in UTC-8 submits a request at 11 PM local time (which is 7 AM the next day in UTC), the pricing resolution will use tomorrow's date from the client's perspective. This could resolve a different pricing version than expected.

For FinOps accuracy, date handling should be explicit. If `usage_date` is omitted, the behavior should be documented as "the server's current UTC date" and clients should be encouraged to always provide the date explicitly when calculating historical costs.

**Proposed Resolution:** Document the behavior clearly in the endpoint description. Optionally use `date.today()` with a UTC comment. The fix requires no code change — only documentation: add to the endpoint description "If omitted, defaults to the current server UTC date."

**Estimated Effort:** 15 minutes

---

### REV-05 — MEDIUM: `GET /pricing/providers` Ignores `organization_id` Parameter

**Severity:** MEDIUM
**Category:** Multi-Tenant Isolation
**File:** `app/api/v1/pricing.py`, lines 159–178

The `GET /pricing/providers` endpoint declares `organization_id` as a required query parameter but the SQL query does not use it:

```python
stmt = (
    select(distinct(MP.provider))
    .where(
        MP.deleted_at.is_(None),
        MP.is_active.is_(True),
    )
    .order_by(MP.provider)
)
```

The `organization_id` is accepted but silently ignored. This means all authenticated users see the same list of providers regardless of which organization they belong to. In a multi-tenant environment, providers available to Organization A should not necessarily be visible to Organization B.

In EP-09's current deployment model (where pricing is platform-wide, not per-organization), this is not a functional bug. However, the accepted-but-ignored parameter creates a false contract: API consumers would reasonably expect `organization_id` to filter results, and they would be wrong.

**Proposed Resolution:** Option A — remove the `organization_id` parameter from this endpoint entirely, since pricing is platform-wide in EP-09. Option B — add an `organization_id` filter to the query once per-organization pricing is supported (EP-10). If Option A is chosen, document in the endpoint description that providers are platform-wide.

**Estimated Effort:** 30 minutes

---

### REV-06 — LOW: `AggregationService.build_daily_summaries` Imports Inside Loop

**Severity:** LOW
**Category:** Code Quality
**File:** `app/analytics/aggregation.py`, lines 96–97

```python
for row in rows:
    from datetime import datetime, UTC
    now = datetime.now(UTC)
```

The `from datetime import datetime, UTC` import is inside the `for` loop. Python caches module imports after the first load, so this does not cause a performance problem. However, it is unconventional — imports belong at the top of the file. The `UTC` constant was added to Python 3.11's `datetime` module.

**Proposed Resolution:** Move the import to the top of the file alongside the other imports. This is a pure code style fix with no behavioral change.

**Estimated Effort:** 5 minutes

---

### REV-07 — LOW: `AnalyticsService.get_top_models()` and `get_top_projects()` Apply Limit in Python

**Severity:** LOW
**Category:** Performance / Scalability
**File:** `app/analytics/service.py`, lines 110–132

```python
async def get_top_models(self, ..., limit: int = 10) -> list[dict]:
    all_models = await self._cost_repo.get_totals_by_model(organization_id, start_date, end_date)
    return all_models[:limit]
```

This fetches ALL models for the date range from the DB, then slices the list in Python. The repository query already returns results sorted by `total_cost DESC` (ORDER BY applied in the SQL), so the top-N result is always the first N rows. However, fetching all rows (potentially hundreds of model/currency combinations) to return only 10 is wasteful.

For the current scale (small number of models per organization in EP-09), this is not a problem. As organizations accumulate long model usage histories, this could become a performance concern.

**Proposed Resolution:** Add a `limit` parameter to `get_totals_by_model()` and `get_totals_by_project()` in the repository, applying it in SQL as `LIMIT :limit`. The existing sorting already produces the correct order for top-N queries.

**Estimated Effort:** 1 hour

---

## Architecture Decisions Reviewed

### ADR-09-01: Why `Numeric(20,10)` for Prices and `Numeric(20,8)` for Costs

**Decision:** Two different precision levels for price-per-token and computed cost fields.

**Review:** Correct and well-reasoned. Price-per-token values must represent sub-cent fractions (e.g., $0.000000015 per token). `NUMERIC(20, 10)` allows 10 decimal places, which is sufficient for all current AI provider pricing. Computed costs are the product of token counts (integers) and per-token prices. After multiplication, the result requires at most 10 decimal places of the price plus the integer digits of the token count. Quantizing to 8 decimal places (NUMERIC(20, 8)) is a reasonable financial precision for a billing amount, while reducing storage compared to 10dp. The 20-digit total precision prevents overflow even for organizations with billions of tokens.

**Verdict:** Accepted. The two-level precision strategy is correct.

---

### ADR-09-02: Why 1:1 Between UsageEvent and UsageCostRecord

**Decision:** One cost record per usage event, enforced by `UNIQUE(usage_event_id)`.

**Review:** This is the correct design. It preserves the cost audit trail at the individual API call granularity — the same granularity as the usage events. Aggregating multiple events into a single cost record would make retroactive repricing difficult (which events were included? what were their individual costs?). The 1:1 design also means that re-running cost calculation for the same event is safe (upsert replaces the existing record).

**Verdict:** Accepted.

---

### ADR-09-03: Why `DailyCostSummary` Is Pre-Aggregated

**Decision:** Build a separate `daily_cost_summaries` table rather than querying `usage_cost_records` directly for all analytics.

**Review:** The pre-aggregation strategy is correct for production analytics workloads. `usage_cost_records` is an append-heavy table that will grow to millions of rows. Aggregating millions of rows for every dashboard page load would be expensive. Pre-aggregated daily summaries reduce this to at most 365 rows per year per (org, provider, model) combination. The upsert pattern on `daily_cost_summaries` means summaries can be rebuilt idempotently after pricing corrections.

In EP-09, the analytics service reads from `usage_cost_records` directly (not the daily summaries) because the aggregation job is not yet scheduled. This is the correct transitional approach — the API contract is defined against `usage_cost_records`, and EP-10 can switch to `daily_cost_summaries` transparently without changing the API layer.

**Verdict:** Accepted.

---

### ADR-09-04: Why `CALCULATION_VERSION` Exists

**Decision:** Store a calculation version string on every `UsageCostRecord`.

**Review:** This is a forward-looking design decision. The "1.0" version string has no operational impact today but enables future workflows:
1. When the calculation formula changes (e.g., adding volume discounts), all records with version "1.0" can be selectively repriced
2. Audit trails can show which pricing algorithm produced each cost
3. Multi-version cost records can coexist during a rolling repricing operation

The cost is minimal — a VARCHAR(32) column on every cost record. The benefit is significant when repricing invariants need to be maintained.

**Verdict:** Accepted.

---

### ADR-09-05: Why Analytics Is Read-Only

**Decision:** `AnalyticsService` is structurally read-only — it has no session and no write paths.

**Review:** Correct architectural boundary. Analytics services that can write financial records are a hazard: a bug in the analytics layer could corrupt billing data. By making `AnalyticsService` structurally read-only (constructor accepts only repositories, never a session), the constraint is enforced without relying on convention or code review discipline. This follows the same pattern as the EP-08 review recommendation for read/write separation.

**Verdict:** Accepted.

---

### ADR-09-06: Why Org Membership Auth Is Deferred to EP-10

**Decision:** EP-09 validates JWT but does not enforce organization membership or RBAC permissions.

**Review:** This is the correct phased approach, consistent with the pattern established in EP-08. The technical reason: org membership verification requires either (a) the authenticated user's JWT to contain org claims (not yet configured in EP-09), or (b) a database lookup to verify membership. Both require infrastructure (JWT claim design, membership lookup service) that are properly owned by EP-10.

The risk is that org membership and RBAC gaps are known security limitations that must be tracked. The code comments document the deferral explicitly. The production readiness assessment marks these as FAIL items that block production promotion.

**Verdict:** Accepted with the understanding that EP-10 MUST close these gaps before production.

---

## Scorecard

| Category | Score | Notes |
|----------|-------|-------|
| Data Model Design | 9/10 | Correct types, clean constraints, good FK strategy |
| Pricing Engine Architecture | 9/10 | Stateless, deterministic, correct rounding |
| Repository Pattern | 9/10 | Correct ON CONFLICT names, consistent upsert |
| Service Layer Design | 8/10 | Read/write separation correct; Python-side limit is minor |
| API Design | 7/10 | providers endpoint ignores org_id; cursor gap in filtered path |
| Financial Accuracy | 9/10 | Decimal throughout; multi-currency sum gap documented |
| Test Coverage | 9/10 | 135 tests, precision assertions, auth guards |
| Code Quality | 9/10 | Structured logging, no silent exceptions, import-in-loop minor |
| **Overall** | **8.5/10** | Strong; ready for EP-10 with tracked findings |

---

## Required Changes Before EP-10 Production Deployment

| ID | Severity | Finding | Status |
|----|----------|---------|--------|
| REV-01 | LOW | Cursor pagination not propagated in filtered `/pricing/models` list path | OPEN |
| REV-02 | MEDIUM | `get_totals_by_org()` sums across currencies — incorrect in multi-currency deployments | OPEN |
| REV-03 | LOW | Soft-delete filter applied manually in aggregation queries (maintainability) | OPEN |
| REV-04 | LOW | `usage_date` defaults to server's local date, not UTC | OPEN |
| REV-05 | MEDIUM | `GET /pricing/providers` accepts but ignores `organization_id` parameter | OPEN |
| REV-06 | LOW | Import inside for loop in `AggregationService.build_daily_summaries` | OPEN |
| REV-07 | LOW | `get_top_models/projects` fetch all rows and slice in Python | OPEN |

REV-02 and REV-05 should be resolved before EP-10 begins, as they affect API contract correctness.

---

## EP-10 Prerequisites

The following items are explicitly deferred from EP-09 and must be addressed in EP-10:

1. **Wire PricingEngine into collection pipeline** — `UsageCostRecord` is empty until EP-10 calls `PricingEngine.calculate_event_cost()` after each `UsageEvent` is persisted.

2. **Org membership verification** — `organization_id` must be derived from JWT claims and verified against the organizations table before any analytics query is executed.

3. **RBAC enforcement** — Add `RequirePermission(Permission.BILLING_READ)` on analytics GET endpoints, `RequirePermission(Permission.BILLING_WRITE)` on pricing POST endpoints.

4. **Scheduled aggregation job** — `AggregationService.rebuild_range()` must be called on a schedule (nightly cron or event-triggered) to keep `daily_cost_summaries` current.

5. **Pricing cascade recalculation** — When a pricing record is updated, existing cost records computed under the old pricing should be queued for recalculation.

6. **Multi-currency cost summary** — Resolve REV-02 before any non-USD pricing is configured.

7. **Budget alerts and forecasting** — Not in EP-09 scope; planned for EP-10+.

8. **Dashboard UI** — Not in EP-09 scope; planned for EP-10+.

---

## Final Decision

**APPROVED WITH MINOR CHANGES**

EP-09 is architecturally sound and may proceed to EP-10. The two MEDIUM findings (REV-02, REV-05) should be resolved at the start of EP-10 before new features are built on top of these endpoints. The LOW findings may be resolved in EP-10 or tracked as backlog items. No findings prevent the code from being merged and deployed to development/staging.
