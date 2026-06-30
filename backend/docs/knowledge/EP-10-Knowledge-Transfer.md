# EP-10 Knowledge Transfer: Dashboard API & Executive Analytics Layer

**Epic:** EP-10
**Features:** F-060 through F-066
**Status:** Complete
**Date:** 2026-06-30
**Author:** Engineering Team

---

## Section 1 — Executive Summary

### What EP-10 Implemented

EP-10 delivers the Dashboard API & Executive Analytics Layer for AI FinOps. It spans features F-060 through F-066 and introduces one new application package, one new schema file, one new API router file, and 78 tests.

| Feature | Artifact | Description |
|---------|----------|-------------|
| F-060 | `GET /v1/dashboard/overview` | Executive overview: total/today/month spend, active providers/models, collection status |
| F-061 | `GET /v1/dashboard/time-series` | Cost time series with daily, weekly, and monthly granularities |
| F-062 | `GET /v1/dashboard/providers` | Per-provider cost and usage breakdown |
| F-063 | `GET /v1/dashboard/models` | Per-model cost and usage breakdown with limit support |
| F-064 | `GET /v1/dashboard/organization` | Composite endpoint: overview + providers + top 5 models + projects + 30-day trend |
| F-065 | `GET /v1/dashboard/projects` | Per-project cost and usage breakdown |
| F-066 | `GET /v1/dashboard/kpis` | Derived KPIs: highest-cost provider/model, avg cost per request and per token |
| Cross-cutting | `DashboardService` | Thin orchestration layer — composes responses from AnalyticsService and repositories |
| Cross-cutting | `app/schemas/dashboard.py` | 9 Pydantic DTOs with Decimal-as-string serialization |

### Business Purpose: Why Executive Dashboards Matter for FinOps

The Cost & Analytics Engine (EP-09) stores pre-computed costs with full attribution. EP-10 exposes that data through purpose-built dashboard endpoints optimized for executive consumption. Finance teams, engineering leads, and product managers need:

- **Instant spend visibility**: How much did we spend today? This month? All time?
- **Provider comparison**: Is OpenAI or Anthropic costing us more?
- **Model efficiency analysis**: Which model has the lowest cost per token?
- **Project attribution**: Which product or team is driving AI spend?
- **Trend analysis**: Is our AI spending growing week-over-week?

The dashboard layer answers all of these questions without requiring consumers to perform aggregation themselves.

### Technical Purpose: Orchestration, Not Computation

EP-10 introduces zero new business logic. All cost calculations and aggregations were implemented in EP-09. The `DashboardService` is a pure orchestration layer that:

1. Accepts high-level requests from the API layer
2. Delegates to `AnalyticsService` and `UsageCostRecordRepository`
3. Composes and reshapes the response for frontend consumption
4. Serializes `Decimal` values as strings at the DTO boundary

---

## Section 2 — Dashboard Architecture

### Complete Layered Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    HTTP Client (Browser/CLI)                     │
└───────────────────────────┬─────────────────────────────────────┘
                            │ GET /v1/dashboard/*
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│               Dashboard API Layer (EP-10)                        │
│    app/api/v1/dashboard.py                                      │
│    7 endpoints — thin controllers, no business logic            │
│    JWT auth via CurrentUser dependency (matching EP-09)         │
└───────────────────────────┬─────────────────────────────────────┘
                            │ calls
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│               Dashboard Service (EP-10)                          │
│    app/dashboard/service.py                                     │
│    DashboardService — orchestration only                        │
│    Lazy-instantiates AnalyticsService + repositories            │
└──────────┬──────────────────────────────────┬───────────────────┘
           │ calls                             │ calls
           ▼                                  ▼
┌─────────────────────┐            ┌──────────────────────────────┐
│  AnalyticsService   │            │  UsageCostRecordRepository   │
│  (EP-09)            │            │  (EP-09)                     │
│  get_provider_       │            │  get_totals_by_org()         │
│  breakdown()        │            │  get_totals_by_provider()    │
│  get_model_         │            │  get_daily_trend()           │
│  breakdown()        │            │                              │
│  get_top_models()   │            └──────────────────────────────┘
│  get_daily_trend()  │
└─────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│               Cost & Analytics Engine (EP-09)                    │
│    usage_cost_records table                                     │
│    daily_cost_summaries table                                   │
│    model_pricing table                                          │
└─────────────────────────────────────────────────────────────────┘
```

### Request Flow

1. Client sends `GET /v1/dashboard/overview?organization_id=...`
2. FastAPI validates JWT via `CurrentUser` dependency
3. Endpoint function instantiates `DashboardService(session=db)`
4. `DashboardService.get_overview()` calls `UsageCostRecordRepository` three times (all-time, month-to-date, today-only) and queries `UsageCollectionRun` for status
5. Results are composed into a dict
6. Endpoint constructs `OverviewResponse` DTO, serializing all `Decimal` fields as `str`
7. FastAPI serializes to JSON and returns 200

### Package Structure

```
app/
  dashboard/
    __init__.py          # empty package marker
    service.py           # DashboardService
  api/v1/
    dashboard.py         # 7 router endpoints
  schemas/
    dashboard.py         # 9 Pydantic DTOs
tests/
  test_ep10.py           # 78 tests
docs/
  knowledge/EP-10-Knowledge-Transfer.md
  engineering/EP-10-Completion-Report.md
  architecture/Dashboard-API-Architecture.md
```

---

## Section 3 — Dashboard Service

### Design Contract

`DashboardService` accepts an `AsyncSession` and lazy-instantiates all downstream dependencies inside methods. This avoids circular imports (the same pattern used in EP-09 aggregation service) and ensures each method request uses a fresh repository instance tied to the current transaction.

### Method Reference

#### `get_overview(organization_id, today=None) -> dict`

Composes executive-level summary. Makes five DB queries:
1. `get_totals_by_org(org, 2000-01-01, today)` — all-time spend
2. `get_totals_by_org(org, month_start, today)` — month-to-date spend
3. `get_totals_by_org(org, today, today)` — today's spend
4. `get_totals_by_provider(...)` — counts distinct providers
5. `get_totals_by_model(...)` — counts distinct (provider, model) pairs
6. Direct SQLAlchemy query on `UsageCollectionRun` — latest run status

Returns: `{total_spend, today_spend, month_spend, total_tokens, total_requests, active_providers, active_models, collection_status, last_collection_at, currency}`

**Note:** All-time queries use `date(2000, 1, 1)` as the start sentinel. This is intentional — cost records do not exist before usage collection began, so this produces correct results without schema changes.

#### `get_time_series(organization_id, start_date, end_date, granularity="daily") -> list[dict]`

Calls `AnalyticsService.get_daily_trend()` then applies Python-side grouping:
- `daily`: returns raw rows as-is
- `weekly`: groups by ISO week key (`YYYY-Www`)
- `monthly`: groups by month key (`YYYY-MM`)
- Unknown granularity: falls back to daily with a structlog warning

Grouping in Python (rather than SQL) is appropriate here because: (1) the date range is bounded by the query params, (2) the daily data is already pre-aggregated, and (3) ISO week logic is trivial in Python but complex across database dialects.

#### `get_provider_breakdown(organization_id, start_date, end_date) -> list[dict]`

Calls `AnalyticsService.get_provider_breakdown()`. Computes `avg_cost_per_request = total_cost / record_count` in Python. Guard against division by zero: returns `Decimal(0)` when `record_count == 0`.

#### `get_model_breakdown(organization_id, start_date, end_date, limit=20) -> list[dict]`

Calls `AnalyticsService.get_top_models()` with the SQL LIMIT applied in the repository (not Python-side). Default limit is 20; maximum enforced at API layer is 100.

#### `get_project_breakdown(organization_id, start_date, end_date) -> list[dict]`

Calls `AnalyticsService.get_project_breakdown()`. Converts `project_id` UUID to string for DTO compatibility. Preserves `None` for unattributed cost records.

#### `get_kpis(organization_id, start_date, end_date) -> dict`

Makes three queries:
1. Provider breakdown → `highest_cost_provider` (max by `total_cost`)
2. Model breakdown → `highest_cost_model` (max by `total_cost`)
3. `get_totals_by_org()` → `avg_cost_per_request`, `avg_cost_per_token`

All division uses `Decimal` arithmetic. Returns `None` for KPIs when no data exists.

---

## Section 4 — DTOs / Response Models

All schemas are in `app/schemas/dashboard.py`. They use Pydantic v2 with `model_config = ConfigDict(from_attributes=True)`.

**Critical invariant:** All `Decimal` monetary values are typed as `str` in the schema. This ensures JSON serialization produces strings, not floats. Floats lose precision for monetary amounts (e.g., `0.1 + 0.2 != 0.3` in IEEE 754).

| Schema | Purpose |
|--------|---------|
| `OverviewResponse` | F-060: executive summary |
| `TimeSeriesPoint` | Single time bucket in a trend |
| `TimeSeriesResponse` | F-061: full time series with aggregates |
| `ProviderMetrics` | Cost metrics for one provider |
| `ProviderBreakdownResponse` | F-062: provider list with total |
| `ModelMetrics` | Cost metrics for one model |
| `ModelBreakdownResponse` | F-063: model list with total |
| `ProjectMetrics` | Cost metrics for one project |
| `ProjectBreakdownResponse` | F-065: project list with total |
| `KPIResponse` | F-066: derived KPIs |

### Serialization Pattern

```python
# In endpoint function:
return OverviewResponse(
    total_spend=str(data["total_spend"]),   # Decimal -> str
    today_spend=str(data["today_spend"]),
    ...
)
```

The conversion `str(decimal_value)` uses Python's default `Decimal.__str__` which produces the full decimal representation without exponential notation for reasonable values (e.g., `"100.00"`, `"0.00002000"`).

---

## Section 5 — REST API Endpoints

### Base URL: `/v1/dashboard`

All endpoints are GET-only (read-only). All require JWT auth via `CurrentUser`.

#### F-060 `GET /overview`
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| organization_id | UUID | Yes | Organization to query |
| currency | str | No (default "USD") | Target currency |

Response: `OverviewResponse`

#### F-061 `GET /time-series`
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| organization_id | UUID | Yes | |
| start_date | date | Yes | ISO 8601 |
| end_date | date | Yes | ISO 8601 |
| granularity | str | No (default "daily") | "daily", "weekly", "monthly" |
| currency | str | No (default "USD") | |

Response: `TimeSeriesResponse`

#### F-062 `GET /providers`
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| organization_id | UUID | Yes | |
| start_date | date | Yes | |
| end_date | date | Yes | |
| currency | str | No | |

Response: `ProviderBreakdownResponse`

#### F-063 `GET /models`
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| organization_id | UUID | Yes | |
| start_date | date | Yes | |
| end_date | date | Yes | |
| limit | int | No (default 20, max 100) | |
| currency | str | No | |

Response: `ModelBreakdownResponse`

#### F-064 `GET /organization`
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| organization_id | UUID | Yes | |
| start_date | date | No | Defaults to first of current month |
| end_date | date | No | Defaults to today |
| currency | str | No | |

Response: `dict` with keys: `organization_id`, `period_start`, `period_end`, `currency`, `overview`, `provider_breakdown`, `top_models`, `project_breakdown`, `daily_trend`

#### F-065 `GET /projects`
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| organization_id | UUID | Yes | |
| start_date | date | Yes | |
| end_date | date | Yes | |
| currency | str | No | |

Response: `ProjectBreakdownResponse`

#### F-066 `GET /kpis`
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| organization_id | UUID | Yes | |
| start_date | date | Yes | |
| end_date | date | Yes | |
| currency | str | No | |

Response: `KPIResponse`

---

## Section 6 — Security Model

### Current State (EP-10)

EP-10 matches the EP-09 security model exactly:

- Every endpoint requires a valid JWT Bearer token
- Auth is enforced via the `CurrentUser` dependency from `app/auth/dependencies.py`
- Missing or invalid tokens return `401 Unauthorized`
- `organization_id` is accepted as a query parameter — the caller asserts which org they want

### Deferred to EP-11

| Item | Description |
|------|-------------|
| Org membership verification | Verify the authenticated user is a member of the requested organization |
| RBAC enforcement | Check `BILLING_READ` permission before returning cost data |
| JWT-derived org_id | Derive `organization_id` from JWT claims rather than trusting query parameter |

The comment `# NOTE: org membership verification is deferred to EP-11` appears on each endpoint that requires it, matching the pattern established in EP-09.

---

## Section 7 — Performance Strategy

### Pre-aggregated Data

All dashboard queries run against `usage_cost_records` which has indexes on `(organization_id, usage_date)`. The `DailyCostSummary` table (built by EP-09's `AggregationService`) exists for future optimization but is not used in EP-10 — the cost record aggregation queries are fast enough for the MVP dashboard.

### Query Count Per Endpoint

| Endpoint | DB Queries |
|----------|-----------|
| `/overview` | 6 (3x org totals, providers, models, collection run) |
| `/time-series` | 1 |
| `/providers` | 1 |
| `/models` | 1 |
| `/organization` | 9 (overview x6 + providers + models + projects + trend) |
| `/projects` | 1 |
| `/kpis` | 3 (providers, models, org totals) |

### No N+1 Queries

All aggregation is done in a single SQL query per dimension. There are no loops that issue per-row queries. The repository methods return aggregated results in one round-trip.

### Future Caching

The `/overview` and `/organization` endpoints are the best candidates for Redis caching (TTL of 60–300 seconds) because:
1. They issue the most DB queries
2. Their inputs are bounded (org_id + date range)
3. They are read-only — cache invalidation is straightforward

---

## Section 8 — Testing Strategy

### Test Count: 78

| Test Class | Count | What It Tests |
|------------|-------|---------------|
| `TestDashboardSchemas` | 13 | Schema construction, null handling, Decimal-as-string invariant |
| `TestDashboardServiceOverview` | 5 | `get_overview()` with/without collection run, empty data, provider count |
| `TestDashboardServiceTimeSeries` | 5 | Daily/weekly/monthly grouping, empty data, unknown granularity |
| `TestDashboardServiceProviderBreakdown` | 4 | Provider list, avg cost calculation, zero-division guard |
| `TestDashboardServiceModelBreakdown` | 3 | Model list, limit passthrough, empty |
| `TestDashboardServiceProjectBreakdown` | 3 | Project list, null project_id, empty |
| `TestDashboardServiceKPIs` | 7 | KPI derivation, none-when-empty, Decimal types |
| `TestDashboardAuthGuards` | 7 | Every endpoint returns 401 without JWT |
| `TestDashboardValidationGuards` | 3 | Missing org_id, invalid date, limit > 100 |
| `TestOverviewEndpoint` | 3 | 200 response, schema shape, Decimal serialized as string |
| `TestTimeSeriesEndpoint` | 5 | Daily/weekly/monthly 200, empty 200, total_cost is string |
| `TestProviderEndpoint` | 2 | 200 response, empty 200 |
| `TestModelsEndpoint` | 3 | 200, limit param, empty 200 |
| `TestOrganizationEndpoint` | 3 | 200, composite structure, optional date defaults |
| `TestProjectsEndpoint` | 2 | 200, empty 200 |
| `TestKPIsEndpoint` | 3 | 200, empty 200, string fields |
| `TestDecimalSerializationInAPI` | 3 | String serialization for providers, models, projects |
| `TestRouterRegistration` | 2 | All 7 routes in OpenAPI spec, "dashboard" tag present |

### Testing Philosophy

- All tests are hermetic — no network calls, no live database
- Service tests use `patch()` to replace internal lazy-instantiated dependencies
- API tests use FastAPI's `dependency_overrides` for auth and DB
- Empty data always returns 200 with empty collections (never 404)
- Decimal serialization is tested at every level (schema, service, API)

---

## Section 9 — Top 25 Engineering Concepts for EP-10

1. **Orchestration Layer Pattern**: `DashboardService` composes responses from existing services without adding business logic — a deliberate architectural separation.

2. **Decimal-as-String Serialization**: All monetary values are typed as `str` in Pydantic schemas to prevent JSON float precision loss.

3. **Lazy Dependency Instantiation**: Repositories and `AnalyticsService` are instantiated inside service methods (not in `__init__`) to avoid circular imports and follow the EP-08/09 pattern.

4. **Thin Controllers**: API endpoint functions contain no business logic — they instantiate the service, call one method, and construct the response DTO.

5. **ISO Week Grouping**: Weekly time series uses Python's `date.isocalendar()` — produces ISO 8601-compliant week keys (`YYYY-Www`) without SQL dialect-specific week functions.

6. **Sentinel Date for All-Time Queries**: `date(2000, 1, 1)` is used as the start date for "all-time" cost queries. Safe because no AI usage data exists before the system was deployed.

7. **Guard Against Division by Zero**: KPI and provider breakdown calculations check `record_count > 0` and `total_tokens > 0` before dividing — returns `Decimal(0)` or `None` as appropriate.

8. **`from __future__ import annotations`**: All new production files include this to enable forward references and improve type annotation ergonomics.

9. **JWT-First Auth**: The `CurrentUser` dependency runs before parameter validation — unauthenticated requests return 401 before FastAPI validates query parameters.

10. **Composite Endpoint Pattern (F-064)**: `/organization` issues multiple `DashboardService` calls and composes them into a single response object — reduces client-side round-trips for the main dashboard view.

11. **`structlog` Logging**: All service-level logs use `structlog.get_logger(__name__)` with structured key-value pairs — no f-string interpolation in log calls.

12. **Empty List = 200 Not 404**: Endpoints that return list data always return 200 with an empty list when no data exists. A 404 would be misleading — the organization exists, there's just no data yet.

13. **UTC-Safe Date Derivation**: `datetime.now(tz=UTC).date()` is used for the default `today` date — prevents off-by-one errors in deployments spanning timezone boundaries.

14. **SQL LIMIT in Repository**: `get_top_models()` applies `LIMIT` in SQL via the repository, not Python-side slicing — consistent with the EP-09 `RH-05` fix.

15. **`AnalyticsService` as the Aggregation Contract**: `DashboardService` calls `AnalyticsService` methods rather than calling the repository directly for breakdown queries — preserves the separation established in EP-09.

16. **Pydantic `ConfigDict(from_attributes=True)`**: Enables ORM model construction from SQLAlchemy objects, though DTOs are never populated from ORM models directly in EP-10 (they're built from dicts).

17. **FastAPI `Query()` Annotation Pattern**: Parameters use `Annotated[uuid.UUID, Query(description="...")]` — consistent with EP-09 analytics endpoints and produces correct OpenAPI documentation.

18. **`ge=1, le=100` Constraints on Limit**: The `limit` parameter on `/models` uses FastAPI's `Query(ge=1, le=100)` — violations return 422 before the service is called.

19. **Router Prefix Convention**: The router uses `prefix="/dashboard"` and is included with `prefix="/v1"` in `api/router.py` — produces `/v1/dashboard/*` paths consistent with all other v1 endpoints.

20. **`tags=["dashboard"]`**: The router tag produces grouped OpenAPI documentation and is verified in tests via the `/openapi.json` spec endpoint.

21. **Dependency Injection via `DbDep`**: Database sessions are injected via the `DbDep` type alias (`Annotated[AsyncSession, Depends(get_db)]`) — consistent with all other EP-08/09 endpoints.

22. **ISO Date Strings in Responses**: All `date` values in DTOs are serialized as ISO 8601 strings (`.isoformat()`) — consistent, timezone-agnostic, and readable by all JSON consumers.

23. **Monthly Granularity Key Format**: Monthly buckets use `YYYY-MM` format (e.g., `"2026-06"`) — sortable lexicographically, unambiguous, and parseable by all major date libraries.

24. **`_make_analytics_service()` Helper**: Internal helper method on `DashboardService` centralizes the construction of `AnalyticsService` with its two repository dependencies — makes it easy to patch in tests.

25. **Zero New Business Logic**: The architectural principle for EP-10 is explicitly zero new business logic — all cost calculation, aggregation, and pricing logic remains in EP-09's layers. EP-10 is a pure read/compose/serialize layer.
