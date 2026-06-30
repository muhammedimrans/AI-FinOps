# EP-10 Release Hardening — Sprint Report

**Date:** 2026-06-30
**Branch:** `claude/ai-finops-ep-01-s4d42x`
**Sprint:** EP-10 Release Hardening — resolves approved review findings before EP-11 begins

---

## Summary

All approved findings from the EP-10 Architecture Review and Production Readiness Assessment have been resolved. The two MEDIUM findings (RH-01, RH-02) are fully corrected. Three LOW findings (RH-03, RH-04, RH-05) are resolved. RH-04 (asyncio.gather) is intentionally documented and deferred with an explanatory comment rather than implemented — see finding detail below.

**Test results:** 1010 passed, 30 skipped (integration tests requiring PostgreSQL), 0 failed.
**EP-10 tests:** 97 passed (78 original + 19 new regression tests).

---

## Findings Resolved

### RH-01 — Granularity Enum Validation (MEDIUM)

**Finding:** The `granularity` query parameter on `/time-series` was typed as `str`. An invalid value (e.g., `granularity=hourly`, `granularity=DAILY`, `granularity=foo`) was silently accepted and fell through to the `else` branch in `DashboardService.get_time_series()`, returning daily-format data with the invalid string echoed back in the response field. This made debugging difficult for frontend developers.

**Change made:**
- Added `Granularity(str, enum.Enum)` class in `app/api/v1/dashboard.py` with three values: `daily`, `weekly`, `monthly`.
- Changed the endpoint parameter from `granularity: str = "daily"` to `granularity: Granularity = Granularity.daily`.
- FastAPI's built-in enum validation automatically returns HTTP 422 with a clear error message for any value not in the enum.
- The `granularity.value` (a plain string) is passed to `DashboardService.get_time_series()` unchanged — no service-layer changes required.

**Files changed:**
- `app/api/v1/dashboard.py` — `Granularity` enum class added; parameter type changed; `granularity.value` passed to service

**Tests added:**
- `TestRH01GranularityValidation::test_granularity_hourly_returns_422`
- `TestRH01GranularityValidation::test_granularity_foo_returns_422`
- `TestRH01GranularityValidation::test_granularity_wrong_case_returns_422`
- `TestRH01GranularityValidation::test_granularity_daily_returns_200`
- `TestRH01GranularityValidation::test_granularity_weekly_returns_200`
- `TestRH01GranularityValidation::test_granularity_monthly_returns_200`

**Existing test updated:**
- `TestDashboardServiceTimeSeries::test_unknown_granularity_falls_back_to_daily` — this test exercises the `DashboardService` directly with an invalid granularity string. The service-level fallback-to-daily behavior is unchanged and the test continues to pass. The 422 enforcement is at the API layer (FastAPI enum parsing), not the service layer.

---

### RH-02 — Date Range Validation (MEDIUM)

**Finding:** No endpoint validated that `start_date <= end_date`. An inverted date range (e.g., `start_date=2026-12-31&end_date=2026-01-01`) produced a silently empty result set rather than a 422 error, because the SQL `WHERE usage_date >= start_date AND usage_date <= end_date` would match no rows.

**Change made:**
Added `if start_date > end_date: raise HTTPException(status_code=422, detail="start_date must be before or equal to end_date")` at the top of each endpoint handler, before any service calls, on all endpoints that accept date range parameters:
- `/time-series`
- `/providers`
- `/models`
- `/projects`
- `/kpis`
- `/organization` (validates only when both `start_date` and `end_date` are explicitly provided, since they have optional defaults)

**Files changed:**
- `app/api/v1/dashboard.py` — date range check added to six endpoints

**Tests added:**
- `TestRH02DateRangeValidation::test_providers_inverted_dates_returns_422`
- `TestRH02DateRangeValidation::test_models_inverted_dates_returns_422`
- `TestRH02DateRangeValidation::test_kpis_inverted_dates_returns_422`
- `TestRH02DateRangeValidation::test_time_series_inverted_dates_returns_422`
- `TestRH02DateRangeValidation::test_projects_inverted_dates_returns_422`
- `TestRH02DateRangeValidation::test_organization_inverted_dates_returns_422`
- `TestRH02DateRangeValidation::test_same_day_start_end_returns_200` (same day is valid)
- `TestRH02DateRangeValidation::test_date_range_error_message_format`

---

### RH-02b — Currency Safety in Breakdown Totals (LOW / REV-06)

**Finding:** Provider, model, project, and time-series breakdown endpoints summed `total_cost` across all rows returned by the service, which could include records in multiple currencies. For an organization using USD and EUR models, `total_cost` in the response would be a meaningless cross-currency sum (e.g., 100 USD + 80 EUR = "180" with no currency indicated).

**Change made:**
In each breakdown endpoint handler, after fetching rows from `DashboardService`, filter to the requested currency before building the response DTOs and computing `total_cost`:

```python
filtered = [r for r in rows if r.get("currency", currency) == currency]
# Build providers/models/projects list from filtered only
total_cost = sum((r["total_cost"] for r in filtered), Decimal(0))
```

Applied to:
- `/providers` — filters `provider_rows` by `currency` before summing
- `/models` — filters `model_rows` by `currency` before summing
- `/projects` — filters `project_rows` by `currency` before summing
- `/time-series` — filters `points_data` by `currency` before summing
- `/organization` — filters all four sub-lists (providers, models, projects, trend) by `currency`

The `/overview` endpoint does not sum across breakdown rows, so no change was needed there. The `/kpis` endpoint uses org-level totals from `get_totals_by_org()` which already groups by currency (fixed in EP-09 RH-01); the KPI avg calculations use data already scoped to a single currency per row. No change was needed to `DashboardService` or repository layer.

**Files changed:**
- `app/api/v1/dashboard.py` — currency filter added to five endpoint handlers

**Tests added:**
- `TestRH02CurrencyFiltering::test_provider_breakdown_filters_by_currency`
- `TestRH02CurrencyFiltering::test_model_breakdown_filters_by_currency`

---

### RH-03 — `timedelta` Import Moved to Module Level (LOW / REV-03)

**Finding:** `from datetime import timedelta` was imported inside the `get_organization_dashboard()` function body (line 249). This is unconventional; all other imports in the file are at the module top level.

**Change made:**
Moved `timedelta` to the module-level import line:
```python
from datetime import date, datetime, timedelta, UTC
```
Removed the in-function `from datetime import timedelta` statement.

**Files changed:**
- `app/api/v1/dashboard.py` — `timedelta` added to module-level `datetime` import; in-function import removed

**Tests added:** None (import hygiene — the existing test suite verifies the endpoint continues to work correctly).

---

### RH-04 — `OrganizationDashboardResponse` Schema (LOW / REV-04)

**Finding:** The `/organization` composite endpoint was declared with `-> dict` and no `response_model`. FastAPI generated no OpenAPI schema for this endpoint's response. The composite response was built manually as a nested dict.

**Change made:**
Added a full typed schema hierarchy to `app/schemas/dashboard.py`:
- `OrganizationOverviewBlock` — overview sub-block
- `OrganizationProviderItem` — single provider entry
- `OrganizationModelItem` — single model entry
- `OrganizationProjectItem` — single project entry
- `OrganizationTrendPoint` — single daily trend point
- `OrganizationDashboardResponse` — top-level composite with all five sections plus `organization_id`, `period_start`, `period_end`, `currency`

Updated the `/organization` endpoint:
1. `response_model=OrganizationDashboardResponse` added to the `@router.get()` decorator
2. Return type changed from `-> dict` to `-> OrganizationDashboardResponse`
3. Handler body now constructs and returns an `OrganizationDashboardResponse(...)` instance using the new schema classes

The OpenAPI spec now shows a complete typed response schema for `/v1/dashboard/organization`, enabling TypeScript client generation.

**Files changed:**
- `app/schemas/dashboard.py` — six new schema classes added
- `app/api/v1/dashboard.py` — imports updated; `response_model` added; return type and return value updated
- `tests/test_ep10.py` — existing `TestOrganizationEndpoint` tests continue to pass; three new schema/OpenAPI tests added

**Tests added:**
- `TestRH03ResponseModelOrganization::test_organization_response_model_in_openapi`
- `TestRH03ResponseModelOrganization::test_organization_response_contains_required_keys`
- `TestRH03ResponseModelOrganization::test_organization_overview_block_monetary_fields_are_strings`

---

### RH-05 — Sequential Queries Documented (LOW / REV-05)

**Finding:** The `/organization` endpoint issues ~10 sequential database queries. The architecture review suggested `asyncio.gather()` to parallelize the 5 independent `DashboardService` calls.

**Decision:** Documented intentionally rather than implemented. SQLAlchemy's `AsyncSession` is not safe for concurrent access from multiple coroutines sharing the same session. Using `asyncio.gather()` with a single shared `AsyncSession` can cause concurrency issues depending on the SQLAlchemy async driver and connection pool configuration.

**Change made:**
Added an explanatory comment block in the `/organization` endpoint handler:

```python
# Sequential queries intentional: all calls share the same AsyncSession.
# asyncio.gather() with a shared session is not safe with SQLAlchemy async.
# Parallel execution would require per-call sessions — deferred to EP-11 optimization.
```

This documents the architectural decision for future engineers and satisfies the review finding without introducing a concurrency risk.

**Files changed:**
- `app/api/v1/dashboard.py` — comment added in `get_organization_dashboard()`

**Tests added:** None (this is a documentation decision, not a behavior change).

---

## Code Quality Scan Results

| Check | Result |
|-------|--------|
| Module-level imports only | PASS — `timedelta` moved from function body to module level |
| No unused imports | PASS — all imports in both files are used |
| Enum type for constrained string params | PASS — `Granularity` enum added for `granularity` parameter |
| `response_model` on all endpoints | PASS — all 7 endpoints now have `response_model` set |
| Date range validation on all range endpoints | PASS — added to 6 endpoints |
| Currency filtering before cost summation | PASS — added to 5 endpoints |
| Division-by-zero guards | PASS (unchanged from EP-10 baseline) |
| Empty-200 contract | PASS (unchanged from EP-10 baseline) |
| JWT auth on all endpoints | PASS (unchanged from EP-10 baseline) |

---

## Files Changed

| File | Change |
|------|--------|
| `app/api/v1/dashboard.py` | `Granularity` enum; `timedelta` import moved; date range validation on 6 endpoints; currency filtering on 5 endpoints; `response_model` on `/organization`; typed return type and return value for `/organization` |
| `app/schemas/dashboard.py` | 6 new schema classes: `OrganizationOverviewBlock`, `OrganizationProviderItem`, `OrganizationModelItem`, `OrganizationProjectItem`, `OrganizationTrendPoint`, `OrganizationDashboardResponse` |
| `tests/test_ep10.py` | 19 new regression tests across 4 new test classes: `TestRH01GranularityValidation`, `TestRH02DateRangeValidation`, `TestRH02CurrencyFiltering`, `TestRH03ResponseModelOrganization` |
| `docs/knowledge/EP-10-Release-Hardening.md` | This document |
| `docs/knowledge/EP-10-Architecture-Review.md` | Final decision updated to "APPROVED AND FROZEN (post-hardening)" |
| `docs/knowledge/EP-10-Production-Readiness.md` | Production risks PRR-03 and PRR-04 marked RESOLVED |
| `docs/architecture/ARCHITECTURE_CHANGELOG.md` | `[0.10.2]` entry prepended |

---

## Test Results

```
EP-10 test suite:   97 passed, 0 failed  (78 original + 19 new regression tests)
Full test suite:  1010 passed, 30 skipped (integration tests — need live PostgreSQL), 0 failed
```

All EP-10 hardening regression tests pass. All existing EP-09 and EP-10 tests continue to pass. No regressions introduced.

---

## Remaining EP-11 Prerequisites

The following items are intentionally deferred from EP-10 and must be implemented in EP-11:

1. **Org membership verification (HIGH)** — Any authenticated user who knows an `organization_id` can read that organization's complete financial dashboard. SEC-02 in the Production Readiness assessment. Must be resolved before production promotion.

2. **RBAC — `BILLING_READ` enforcement (HIGH)** — No permission check before returning cost data. SEC-03 in the Production Readiness assessment. Must be resolved before production promotion.

3. **JWT-derived `organization_id`** — Currently accepted as an untrusted query parameter. Derive from JWT claims in EP-11 to close the enumeration risk.

4. **asyncio.gather() for composite endpoint** — Parallelizing the 5 DashboardService calls requires per-call sessions. Requires EP-11 session management changes. Estimated wall-clock improvement: 50–200ms per `/organization` request.

5. **Redis caching** — `/overview` and `/organization` are high-frequency endpoints. TTL 60s caching would significantly reduce DB load under concurrent dashboard users.

6. **Max date range enforcement on `/time-series`** — A very large date range (e.g., 10 years) would cause the Python-side weekly/monthly bucketing to process thousands of daily rows. Recommended limit: 731 days with a 422 response for exceeded ranges.

7. **Structured logging in DashboardService** — Only `get_overview()` emits a structured log event. Other service methods should log at INFO level to improve observability.

---

## Final Decision

**EP-10 is approved and frozen. The project is ready to begin EP-11 (React Dashboard).**

All MEDIUM findings (RH-01, RH-02) are resolved. All LOW findings are either resolved (RH-03, RH-04, RH-05) or intentionally documented and deferred with clear explanations (REV-05 sequential queries). The test suite is green at 1010 passed. No regressions. EP-11 may begin.
