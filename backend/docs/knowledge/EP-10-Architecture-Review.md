# EP-10 Architecture Review — Dashboard API & Executive Analytics Layer

**Date:** 2026-06-30
**Reviewers:** Principal Software Architect / Principal API Architect / Staff Backend Engineer
**Subject:** EP-10 Dashboard API & Executive Analytics Layer (F-060–F-071)
**Branch:** `claude/ai-finops-ep-01-s4d42x`
**Scope:** `app/dashboard/`, `app/schemas/dashboard.py`, `app/api/v1/dashboard.py`, `tests/test_ep10.py`

---

## Executive Summary

EP-10 delivers a well-structured dashboard API layer that correctly implements the orchestration-without-computation pattern. The `DashboardService` is genuinely thin: it delegates every aggregation query to EP-09's `AnalyticsService` and repositories, performs only bounded composition logic (selecting the max from a list, computing avg with a zero-guard), and returns plain dicts to the API layer. Controllers are minimal — instantiate service, call one method, construct DTO. No business logic has leaked upward from EP-09.

The DTO layer is correct and consistent. All Decimal monetary fields are typed as `str` in Pydantic schemas, and the endpoint functions convert using `str(Decimal_value)` before DTO construction. The empty-200 contract is enforced across all list endpoints and verified in tests. JWT authentication is applied on every endpoint. The 78-test suite covers schema construction, service unit behavior, auth guards, validation, happy-path API calls, and serialization invariants — a complete test pyramid.

Seven findings are raised. None are CRITICAL. Two are MEDIUM severity. Five are LOW. The most significant findings concern: (REV-01) the `granularity` parameter silently degrading on invalid input rather than returning 422; (REV-02) the absence of `start_date <= end_date` validation; (REV-03) a module-level import (`timedelta`) placed inside an endpoint function body; (REV-04) the `/organization` composite endpoint issuing ~10 sequential queries that could be parallelized; and (REV-05) the composite endpoint returning a raw `dict` without `response_model`, removing runtime validation. Security findings are as expected: org membership verification and RBAC are deferred to EP-11 with explicit code comments.

EP-10 is approved for development and staging deployment. No findings block merging. One MEDIUM finding (REV-01) should be addressed before EP-11 adds the React dashboard, as a React client receiving a degraded daily response for an invalid granularity string would be difficult to debug.

**Overall Score: 8.7 / 10**

**Final Decision: APPROVED AND FROZEN (post-hardening)**

---

## Architecture Score

| Category | Score | Justification |
|----------|-------|---------------|
| API Layer Design | 9/10 | Thin controllers, correct DI, REST conventions followed; composite endpoint missing response_model |
| Service Layer (DashboardService) | 9/10 | Zero business logic, correct delegation chain, lazy import pattern used correctly |
| DTO Design | 9/10 | Correct Decimal→str, from_attributes, Field defaults; minor gap: total_cost in model/project breakdown sums only listed items |
| Authentication / Authorization | 7/10 | JWT on all endpoints (PASS); org membership and RBAC deferred (known, documented) |
| Performance | 8/10 | SQL LIMIT correct, no N+1; composite endpoint has 10 sequential queries; no caching yet (acceptable for EP-10) |
| Test Coverage | 9/10 | 78 tests, full pyramid; minor gap: no test for start_date > end_date edge case |
| Code Quality | 8/10 | Consistent patterns, structlog used correctly; `timedelta` import in function body; unknown granularity silent fallback |
| **Overall** | **8.7/10** | Strong EP-09 delegation pattern, complete test coverage, minor gaps documented |

---

## Architecture Strengths

### S-01 — Genuine Zero-Logic Orchestration Layer

**Files:** `app/dashboard/service.py` (entire file)

The `DashboardService` class docstring states "Contains no business logic" and the code upholds this. Every method makes calls to EP-09's `AnalyticsService` or `UsageCostRecordRepository` and returns their results with minimal reshaping. The only computations present in the service are: (1) `avg_cost = total_cost / record_count if record_count > 0 else Decimal(0)` — a guard-protected division, not domain logic, and (2) `max(rows, key=lambda r: r["total_cost"])` — a Python built-in with no domain semantics. This is the correct pattern for a composed API layer and is cleanly enforced.

### S-02 — Correct Decimal Serialization Pattern

**Files:** `app/api/v1/dashboard.py` (lines 73–75, 159–161, 203–205, etc.), `app/schemas/dashboard.py` (all schema classes)

Every monetary field in every schema is declared as `str` (not `Decimal`, not `float`). The conversion `str(data["total_spend"])` in the endpoint function uses Python's `Decimal.__str__()` which produces lossless string representations (`"100.00"`, `"0.00002000"`) without scientific notation for normal financial values. The schema-level `str` type ensures FastAPI serializes these as JSON strings, not JSON numbers. This is verified by 13+ test assertions across the suite.

The one safe-null pattern is also correct: `str(data["avg_cost_per_request"]) if data["avg_cost_per_request"] is not None else None`. This prevents `str(None)` from producing the string `"None"` in the JSON response — a common and subtle bug that was handled correctly.

### S-03 — SQL LIMIT Correctly Pushed to Repository

**Files:** `app/api/v1/dashboard.py` line 191 (`Query(..., ge=1, le=100)`), `app/dashboard/service.py` line 274 (`svc.get_top_models(..., limit=limit)`), `app/analytics/service.py` line 140 (`self._cost_repo.get_totals_by_model(..., limit=limit)`), `app/repositories/usage_cost_record_repository.py` lines 225–226 (`if limit is not None: stmt = stmt.limit(limit)`)

The limit flows correctly through four layers and is applied at the SQL level. The `ge=1, le=100` FastAPI constraint ensures the limit is validated before the service is called, verified in `test_models_limit_exceeds_max`. This correctly resolves EP-09's REV-07 finding (Python-side slicing was fixed in Release Hardening) and EP-10 inherits the correct behavior.

### S-04 — Empty-200 Contract Consistently Enforced

**Files:** `app/dashboard/service.py` (all methods), `app/api/v1/dashboard.py` (all endpoints), `tests/test_ep10.py` (7 `_empty_returns_200_not_404` tests)

Every list-returning endpoint returns HTTP 200 with an empty list when no data exists. This is implemented naturally: the repository queries return empty lists when no rows match the filter, the service returns empty lists, the API layer constructs DTOs with empty lists (using `Field(default_factory=list)` as the default). No explicit `if len(rows) == 0: raise HTTPException(404)` pattern exists — the empty case works correctly by default.

The `OverviewResponse` also handles the no-data case: `sum(r["total_cost"] for r in all_time_rows) or Decimal(0)` returns `Decimal(0)` when `all_time_rows` is empty (because `sum([])` returns integer `0`, and `0 or Decimal(0)` returns `Decimal(0)`).

### S-05 — JWT Authentication on All Endpoints

**File:** `app/api/v1/dashboard.py` (all 7 route handlers, each has `_user: CurrentUser`)

Every endpoint handler signature includes `_user: CurrentUser` as a dependency. FastAPI evaluates `CurrentUser` before the handler body, so authentication failure returns 401 before any query parameters are validated or any service code runs. This is verified by `TestDashboardAuthGuards` which tests all 7 endpoints without a JWT and asserts 401.

### S-06 — Composite Endpoint as API Bandwidth Optimization

**File:** `app/api/v1/dashboard.py` lines 222–314 (`get_organization_dashboard`)

The `/organization` endpoint collects overview, provider breakdown, top-5 models, project breakdown, and 30-day daily trend in a single HTTP call. This is a significant client-side convenience for the React dashboard page load: 5 sequential API calls (with staggered loading states) become 1 call (single loading state). The hardcoded `limit=5` for top models and the last-30-days window for the trend are reasonable defaults for a dashboard "above-the-fold" view.

### S-07 — Lazy Import Pattern Consistent with Project

**File:** `app/dashboard/service.py` lines 39–57 (`_make_analytics_service`, `_cost_repo`, `_run_repo`)

The three private helper methods use deferred imports inside the method body:
```python
def _make_analytics_service(self):
    from app.analytics.service import AnalyticsService
    from app.repositories.usage_cost_record_repository import UsageCostRecordRepository
    ...
```

This follows the identical pattern used in `UsageCollectionService` (EP-08) and is the correct solution to the circular import risk in the EP package structure. The `if TYPE_CHECKING:` block is present in the file (though empty — `pass`) signaling the pattern is understood.

### S-08 — Division-by-Zero Protection on All Arithmetic

**File:** `app/dashboard/service.py` lines 250–251, 278–280, 349–354

Three arithmetic operations in DashboardService all have zero guards:
- Provider `avg_cost_per_request`: `if record_count > 0 else Decimal(0)`
- Model `avg_cost_per_request`: `if record_count > 0 else Decimal(0)`
- KPI `avg_cost_per_request`: `if total_requests > 0: ... else: None`
- KPI `avg_cost_per_token`: `if total_tokens > 0: ... else: None`

The choice of `Decimal(0)` vs `None` is semantically appropriate: for per-provider and per-model avg, a zero avg when there are no requests is reasonable (no requests → no cost). For org-level KPI averages, `None` is more appropriate — it signals "this KPI is undefined for the given period" rather than "the average is zero."

---

## Architecture Findings

### REV-01 — MEDIUM: Invalid `granularity` Silently Degrades to Daily Without 422

**Severity:** MEDIUM
**Category:** API Contract / Defensive Programming
**File:** `app/dashboard/service.py` lines 223–233, `app/api/v1/dashboard.py` line 104

The `granularity` parameter is typed as `str` (not a `Literal["daily", "weekly", "monthly"]` or an `Enum`). The DashboardService handles `"daily"`, `"weekly"`, and `"monthly"` with explicit `if` branches and falls through to a default case for anything else:

```python
# Unknown granularity falls back to daily
log.warning("unknown_granularity", granularity=granularity)
return [...]  # daily format
```

A client that sends `granularity=weeekly` (typo) or `granularity=DAILY` (wrong case) will receive a daily-format response with no indication that their request was interpreted differently from what they intended. From the client's perspective, the response looks correct (it has `granularity: "weeekly"` echoed back from the TimeSeriesResponse), but the data is structured as daily, not weekly.

The echo-back (`granularity=granularity` in `TimeSeriesResponse`) compounds the confusion: the response says `"granularity": "weeekly"` but the `points[].date` fields are `"2026-06-30"` (daily ISO dates), not `"2026-W26"` (weekly keys).

**Proposed Resolution:** Add a Pydantic `Literal["daily", "weekly", "monthly"]` type for the granularity parameter, or use a `Query` with an explicit enum. FastAPI will then return 422 for invalid values with a clear error message. The silent-fallback behavior should be removed or gated behind a documented `?strict=false` option.

```python
granularity: Annotated[
    Literal["daily", "weekly", "monthly"],
    Query(description="Bucket size: daily, weekly, monthly")
] = "daily"
```

**Effort:** 30 minutes (type annotation change + update test that currently asserts fallback behavior)

---

### REV-02 — MEDIUM: No `start_date <= end_date` Validation

**Severity:** MEDIUM
**Category:** Input Validation
**File:** `app/api/v1/dashboard.py` (all endpoints with `start_date` and `end_date` parameters)

No endpoint validates that `start_date <= end_date`. A client sending `start_date=2026-12-31&end_date=2026-01-01` will receive an empty result set (because the SQL `WHERE usage_date >= start_date AND usage_date <= end_date` will match no rows) rather than a 422 error. This is a silent incorrect-input-produces-empty-data scenario that would be difficult for a frontend developer to debug.

The `/organization` endpoint partially mitigates this by defaulting `end_date` to today and `start_date` to first-of-month when not provided. But when both are provided explicitly with an inverted range, no validation occurs.

**Proposed Resolution:** Add a `@root_validator` or `@model_validator` to each schema, or add date range validation in a shared FastAPI dependency that can be reused across endpoints.

Alternatively, add explicit validation in each endpoint:
```python
if start_date > end_date:
    raise HTTPException(status_code=422, detail="start_date must be on or before end_date")
```

**Effort:** 1 hour (shared validator function + application across 5 endpoints + tests)

---

### REV-03 — LOW: `timedelta` Imported Inside Endpoint Function Body

**Severity:** LOW
**Category:** Code Quality
**File:** `app/api/v1/dashboard.py` line 249

```python
async def get_organization_dashboard(...) -> dict:
    ...
    from datetime import timedelta
    trend_start = today - timedelta(days=29)
```

`timedelta` is imported inside the endpoint function body rather than at the module top level. Python caches module imports so there is no performance impact. However, it is unconventional — all other imports in the file are at the top level. This is the same class of issue as EP-09's REV-06 (resolved in Release Hardening).

**Proposed Resolution:** Move `from datetime import timedelta` to the module-level imports at the top of `app/api/v1/dashboard.py`.

**Effort:** 2 minutes

---

### REV-04 — LOW: `/organization` Composite Endpoint Has No `response_model`

**Severity:** LOW
**Category:** API Contract / Documentation
**File:** `app/api/v1/dashboard.py` lines 222–236

The `/organization` endpoint is declared as:
```python
@router.get("/organization", summary="Composite organization dashboard", ...)
async def get_organization_dashboard(...) -> dict:
```

It lacks `response_model=`. Without `response_model`, FastAPI does not validate the response shape at runtime, does not strip unexpected fields, and does not generate an accurate OpenAPI schema for the endpoint's response. The OpenAPI spec will show this endpoint as returning an untyped object, which limits frontend client generation (e.g., TypeScript type generation tools will produce `any` for this response).

The response is constructed manually as a nested dict with inline `str()` conversion of Decimal values. This works correctly but bypasses the Pydantic validation layer that the other 6 endpoints benefit from.

**Proposed Resolution:** Define a `OrganizationDashboardResponse` Pydantic schema in `app/schemas/dashboard.py` that models the nested structure of the composite response. This also enables test assertions against the typed schema rather than raw dict key checks.

**Effort:** 2–3 hours (schema definition + wiring + test updates)

---

### REV-05 — LOW: Organization Composite Endpoint Issues ~10 Sequential Queries

**Severity:** LOW
**Category:** Performance / Scalability
**File:** `app/api/v1/dashboard.py` lines 244–251

The five DashboardService calls in `get_organization_dashboard()` are executed sequentially with `await`:

```python
overview_data = await svc.get_overview(organization_id, today=today)
provider_rows = await svc.get_provider_breakdown(organization_id, effective_start, effective_end)
model_rows = await svc.get_model_breakdown(organization_id, effective_start, effective_end, limit=5)
project_rows = await svc.get_project_breakdown(organization_id, effective_start, effective_end)
trend_rows = await svc.get_time_series(organization_id, trend_start, today, granularity="daily")
```

Each `await` suspends execution until the previous query completes, even though none of these queries depend on each other's results. The wall-clock time for this endpoint is the sum of all query latencies (~10 DB round-trips), rather than the max (which is what asyncio.gather would achieve).

This is not a blocking concern for EP-10 (the endpoint is functionally correct), but it is a known scalability limitation. As the `usage_cost_records` table grows, this endpoint will become the slowest in the dashboard suite.

**Proposed Resolution:** Wrap independent calls in `asyncio.gather()`:
```python
overview_data, provider_rows, model_rows, project_rows = await asyncio.gather(
    svc.get_overview(organization_id, today=today),
    svc.get_provider_breakdown(...),
    svc.get_model_breakdown(..., limit=5),
    svc.get_project_breakdown(...),
)
trend_rows = await svc.get_time_series(...)  # separate, different date range
```

Note: This requires that the SQLAlchemy `AsyncSession` supports concurrent query execution from multiple coroutines — verify this works with the `AsyncSession` configuration before implementing.

**Effort:** 2 hours (gather wiring + testing for race conditions)

---

### REV-06 — LOW: Provider Breakdown `total_cost` Sums Across Currencies

**Severity:** LOW
**Category:** Financial Accuracy
**File:** `app/api/v1/dashboard.py` lines 167–173

The `ProviderBreakdownResponse.total_cost` and `ModelBreakdownResponse.total_cost` are computed in the endpoint function by summing `r["total_cost"]` across all provider/model rows:

```python
total_cost = sum((r["total_cost"] for r in rows), Decimal(0))
```

If the organization uses both USD-priced and EUR-priced models, `rows` may contain both a `{"provider": "openai", "currency": "USD", "total_cost": Decimal("100")}` and a `{"provider": "anthropic", "currency": "EUR", "total_cost": Decimal("80")}`. The `total_cost` in the response would then be `Decimal("180")` — a cross-currency sum that is financially meaningless.

This is a lower-severity version of EP-09's REV-02 (which was resolved for `get_totals_by_org` but not for this computed total-across-rows pattern). In single-currency deployments (the current standard), this is correct.

**Proposed Resolution:** When `rows` contains records from multiple currencies, either (a) compute `total_cost` only for the primary currency, (b) return `total_cost: null` with a note that multi-currency summation is not supported, or (c) return a `cost_by_currency` breakdown in the response (consistent with `CostSummaryResponse` in EP-09).

**Effort:** 2 hours (response schema change + service/endpoint update + tests)

---

### REV-07 — LOW: No Date Range Validation in `/organization` When Both Dates Are Provided

**Severity:** LOW
**Category:** Input Validation
**File:** `app/api/v1/dashboard.py` lines 238–240

The `/organization` endpoint defaults start/end dates when not provided:
```python
effective_end = end_date or today
effective_start = start_date or effective_end.replace(day=1)
```

When only `start_date` is provided (but not `end_date`), `effective_end = today` and `effective_start = start_date`. This is correct.

When only `end_date` is provided (but not `start_date`), `effective_start = end_date.replace(day=1)` (first of the end month). This is a reasonable default.

However, when both are provided and `start_date > end_date`, the logic does not catch this — same as REV-02 above, but this endpoint has an additional subtlety: the `daily_trend` window always uses `today - timedelta(days=29)` to `today`, independent of the provided date range. This means the `daily_trend` section can be correct even when the `period_start`/`period_end` window is inverted — further obscuring the error for frontend developers.

**Proposed Resolution:** Same as REV-02 — add explicit date range validation before any service calls.

**Effort:** 30 minutes (validation + test)

---

## Architecture Decisions Reviewed

### ADR-10-01: Why `/organization` Returns `dict` Rather Than a Typed Response Model

**Decision:** The composite endpoint returns `-> dict` without `response_model`.

**Review:** The composite response has five nested sections (overview, providers, models, projects, trend), each with slightly different field names from the typed DTOs used by the individual endpoints. Defining a composite schema that mirrors this structure would be significant boilerplate (a new schema class with 5 nested list/object fields) and would need to be kept in sync as the individual endpoint schemas evolve.

The tradeoff is: less boilerplate now vs. no runtime response validation and no generated OpenAPI schema. This is a reasonable tradeoff for an internal API in EP-10. However, REV-04 recommends defining this schema in EP-11 when the React dashboard is being built — at that point, TypeScript type generation from the OpenAPI spec becomes important.

**Verdict:** Accepted for EP-10. Should be addressed in EP-11.

---

### ADR-10-02: Why Granularity Bucketing Is Python-Side Rather Than SQL GROUP BY

**Decision:** Weekly and monthly grouping in `get_time_series()` is performed in Python by iterating over daily rows returned from SQL.

**Review:** This is the correct approach for EP-10. The alternatives are:

- **SQL GROUP BY EXTRACT(week FROM usage_date)**: Produces calendar weeks (week 1 is Jan 1–7), not ISO weeks. ISO week handling varies by database dialect (`DATE_PART('week', ...)` in PostgreSQL is not ISO; `EXTRACT(ISOYEAR, ...)` and `EXTRACT(WEEK, ...)` would be needed). Complex and dialect-specific.

- **SQL GROUP BY DATE_TRUNC('month', usage_date)**: More straightforward but requires additional SQL formatting and is still dialect-specific.

- **Python-side grouping over pre-fetched daily rows**: Works identically across all databases, ISO week logic is trivial with `date.isocalendar()`, and the data set is bounded (daily data for the requested date range). For typical dashboard ranges (30–90 days), this fetches at most 90 rows from the DB.

The Python-side approach is preferable for a bounded data set where correctness and portability matter more than pushing aggregation to the database.

**Verdict:** Accepted. Document the bounded-range assumption (the approach becomes expensive for multi-year date ranges; add a warning in the service if `(end_date - start_date).days > 365`).

---

### ADR-10-03: Why Org Membership Verification Is Deferred to EP-11

**Decision:** `organization_id` is accepted from the query string without verifying the authenticated user is a member of that organization.

**Review:** This is the same deferral as EP-09. The technical reasons remain valid: org membership verification requires either JWT claims containing org membership (not yet configured) or a database lookup to the `organization_members` table (not yet in scope). The comment at the top of `app/api/v1/dashboard.py` explicitly documents this deferral.

The risk is higher in EP-10 than in EP-09 because the dashboard endpoints aggregate financial data at the organization level — a user who knows (or guesses) another organization's UUID can see that organization's total AI spend, provider breakdown, and model usage. This is a confidentiality concern in multi-tenant production deployments.

**Verdict:** Accepted for EP-10 development/staging. MUST be resolved in EP-11 before production promotion.

---

### ADR-10-04: Why Decimal Is Converted to `str` at the API Layer, Not the Service Layer

**Decision:** `str(data["total_spend"])` is called in the endpoint function, not in `DashboardService.get_overview()`.

**Review:** This is the correct placement. The service layer deals with domain values (`Decimal`) and should remain unaware of serialization concerns (JSON, string conversion). The API layer is the serialization boundary — it is responsible for converting domain types to wire-format types.

If `DashboardService` returned strings, it would be impossible to use the service in a context where the caller needs the actual Decimal value (e.g., a batch job that sums multiple service calls). Keeping `Decimal` in the service and converting to `str` at the DTO boundary maintains clean separation.

**Verdict:** Accepted. Correct design.

---

## Scorecard

| Category | Score | Notes |
|----------|-------|-------|
| API Layer Design | 9/10 | Thin controllers, consistent patterns; composite endpoint missing response_model |
| Service Layer (DashboardService) | 9/10 | Zero business logic; correct lazy imports; falls back silently on invalid granularity |
| DTO Design | 9/10 | All Decimal→str correct; from_attributes set; multi-currency total sum is a minor gap |
| Authentication / Authorization | 7/10 | JWT on all endpoints; org membership and RBAC deferred (documented, expected) |
| Performance | 8/10 | SQL LIMIT correct; no N+1; composite endpoint sequential (known limitation) |
| Test Coverage | 9/10 | 78 tests, full pyramid; missing: start > end date test; granularity case-sensitivity test |
| Code Quality | 8/10 | Consistent patterns; timedelta import in function; unknown granularity silent fallback |
| **Overall** | **8.7/10** | Strong delegation pattern, complete test coverage, minor gaps |

---

## Required Changes Before EP-11

| ID | Severity | Finding | Status |
|----|----------|---------|--------|
| REV-01 | MEDIUM | Invalid granularity silently degrades to daily | ✅ RESOLVED — `Granularity(str, enum.Enum)` added; FastAPI returns 422 for invalid values |
| REV-02 | MEDIUM | No `start_date <= end_date` validation | ✅ RESOLVED — HTTPException(422) added to 6 endpoints |
| REV-03 | LOW | `timedelta` imported inside function body | ✅ RESOLVED — moved to module-level import |
| REV-04 | LOW | `/organization` has no `response_model` | ✅ RESOLVED — `OrganizationDashboardResponse` schema defined; `response_model` set |
| REV-05 | LOW | Composite endpoint sequential queries | ✅ DOCUMENTED — sequential execution intentional (shared AsyncSession not safe for gather); comment added; deferred to EP-11 |
| REV-06 | LOW | Breakdown `total_cost` may sum across currencies | ✅ RESOLVED — currency filter applied before summation in 5 endpoints |
| REV-07 | LOW | No inverted date range validation in `/organization` | ✅ RESOLVED — covered by REV-02 resolution |

All findings resolved in EP-10 Release Hardening sprint (2026-06-30). See `EP-10-Release-Hardening.md` for full details.

---

## EP-11 Prerequisites

The following items are deferred from EP-10 and must be implemented in EP-11:

1. **Org membership verification** — Verify the authenticated user is a member of the `organization_id` provided in the query string. Without this, any authenticated user can view any organization's financial data. SEC-02 in Production Readiness assessment.

2. **RBAC enforcement** — Check `BILLING_READ` permission (or equivalent) before returning cost data from any dashboard endpoint. SEC-03 in Production Readiness assessment.

3. **JWT-derived org_id** — Derive `organization_id` from the authenticated user's JWT claims rather than accepting it as an untrusted query parameter. This closes the org enumeration risk.

4. **`OrganizationDashboardResponse` schema** — Define a typed Pydantic schema for the composite endpoint's response so that the OpenAPI spec is complete and TypeScript client generation works.

5. **`asyncio.gather()` for composite endpoint** — Parallelize the 5 independent DashboardService calls in `get_organization_dashboard()` to reduce wall-clock latency.

6. **Redis caching layer** — Add cache for `/overview` and `/organization` endpoints (TTL 60–300s) to avoid repeated aggregation queries for the same org during active dashboard sessions.

7. **Date range validation** — Shared validator for `start_date <= end_date` across all date-range endpoints.

8. **`granularity` strict validation** — Replace `str` type with `Literal` or `Enum` to return 422 for invalid values.

---

## Final Decision

**APPROVED AND FROZEN (post-hardening)**

EP-10 Release Hardening (2026-06-30) resolved all findings from this review. All MEDIUM findings (REV-01, REV-02) are fully corrected. All LOW findings are resolved or intentionally documented and deferred. Test results: 1010 passed, 0 failed. EP-11 (React Dashboard) may begin.

The security posture (org membership and RBAC deferred) is identical to EP-09 and is acceptable for development/staging. EP-11 MUST close these gaps before production promotion.
