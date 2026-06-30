# EP-10 Knowledge Transfer: Dashboard API & Executive Analytics Layer

**Epic:** EP-10
**Features:** F-060 through F-066 (plus F-064 composite)
**Status:** Complete — Engineering Review Conducted 2026-06-30
**Date:** 2026-06-30
**Authors:** Engineering Team / Principal Software Architect

---

## Section 1 — Executive Summary

### What EP-10 Implemented

EP-10 delivers the Dashboard API & Executive Analytics Layer for AI FinOps, spanning features F-060 through F-066 (with F-064 acting as the composite organization endpoint). It introduces one new application package (`app/dashboard/`), one new schema file (`app/schemas/dashboard.py`), one new API router file (`app/api/v1/dashboard.py`), and 78 tests in `tests/test_ep10.py`.

| Feature | Endpoint | Description |
|---------|----------|-------------|
| F-060 | `GET /v1/dashboard/overview` | Executive overview: total/today/month spend, active providers/models, latest collection run status |
| F-061 | `GET /v1/dashboard/time-series` | Cost time series with daily, weekly (ISO), and monthly granularities |
| F-062 | `GET /v1/dashboard/providers` | Per-provider cost and usage breakdown with computed avg_cost_per_request |
| F-063 | `GET /v1/dashboard/models` | Per-model cost breakdown, SQL LIMIT-controlled, sorted by cost descending |
| F-064 | `GET /v1/dashboard/organization` | Composite: overview + providers + top 5 models + projects + 30-day daily trend |
| F-065 | `GET /v1/dashboard/projects` | Per-project cost and usage breakdown |
| F-066 | `GET /v1/dashboard/kpis` | Derived KPIs: highest-cost provider/model, avg cost per request and per token |
| Cross-cutting | `DashboardService` | Thin orchestration layer — composes responses from AnalyticsService and repositories |
| Cross-cutting | `app/schemas/dashboard.py` | 9 Pydantic DTOs with Decimal-as-string serialization |

### Business Purpose: Why an Executive Dashboard API Layer

The Cost & Analytics Engine (EP-09) stores pre-computed costs with full multi-dimensional attribution across providers, models, projects, and dates. That engine exposes low-level analytics endpoints suitable for programmatic consumers but not for executive dashboards, which require pre-composed, UI-ready responses.

EP-10 answers the questions that finance teams, engineering leads, and FinOps managers ask daily:

- **Instant spend visibility**: How much have we spent today, this month, and all time?
- **Provider comparison**: Is OpenAI or Anthropic costing us more right now?
- **Model efficiency analysis**: Which model has the lowest average cost per request?
- **Project attribution**: Which team or workload is driving the most AI spend?
- **Trend analysis**: Is our AI spending growing week-over-week or month-over-month?
- **One-call dashboard page**: Can the frontend get everything for the main dashboard page in a single HTTP request?

The dashboard layer answers all of these without requiring the UI to perform aggregation, multi-call coordination, or any calculation.

### Why Controllers Are Thin (Orchestration, Not Computation)

`DashboardService` deliberately contains zero business logic. All cost calculations (pricing, aggregation, Decimal arithmetic, ROUND_HALF_UP, currency grouping) were implemented and validated in EP-09. The principle is: once a computation is correct and tested, it should not be re-implemented in a different layer where it might diverge. EP-10 is a pure read-compose-serialize layer that delegates every calculation to the established EP-09 foundation.

This means that if the analytics logic needs to change (e.g., a new rounding rule, a new currency), it changes in one place (EP-09), and all dashboard endpoints automatically reflect it. There is no parallel implementation to keep in sync.

---

## Section 2 — Dashboard Architecture

### ASCII Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         HTTP Client (Browser / CLI / React)                  │
│                         GET /v1/dashboard/* with Bearer JWT                  │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │ HTTPS
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    FastAPI Application — app/api/v1/dashboard.py             │
│                    7 route handlers (F-060 through F-064/065/066)            │
│                    JWT auth: CurrentUser dependency (401 if missing/invalid)  │
│                    DbDep: AsyncSession injected via get_db() dependency       │
│                    response_model: enforced by FastAPI on each endpoint       │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │ DashboardService(session=db)
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                  DashboardService — app/dashboard/service.py                 │
│                  Orchestration only. No SQL. No business logic.              │
│                  Lazy-instantiates AnalyticsService and repositories         │
│                  inside each method via _make_analytics_service(),           │
│                  _cost_repo(), and _run_repo() helper methods.               │
└────────────┬────────────────────────────────────┬───────────────────────────┘
             │ calls for breakdowns / time-series  │ calls for totals / run status
             ▼                                     ▼
┌────────────────────────────┐        ┌─────────────────────────────────────┐
│   AnalyticsService (EP-09) │        │  UsageCostRecordRepository (EP-09)  │
│   app/analytics/service.py │        │  get_totals_by_org()                │
│                            │        │  get_totals_by_provider()           │
│   get_provider_breakdown() │        │  get_totals_by_model()              │
│   get_model_breakdown()    │        │  (Used directly in get_overview()   │
│   get_top_models()         │        │  and get_kpis() for org totals)     │
│   get_project_breakdown()  │        └─────────────────────────────────────┘
│   get_daily_trend()        │
└────────────┬───────────────┘
             │ delegates to
             ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│              UsageCostRecordRepository — detailed aggregation SQL            │
│              usage_cost_records table (PostgreSQL)                           │
│              GROUP BY provider / model / project / date with SQL LIMIT       │
└─────────────────────────────────────────────────────────────────────────────┘
             AND
┌─────────────────────────────────────────────────────────────────────────────┐
│              UsageCollectionRun — queried directly in get_overview()         │
│              SELECT ... ORDER BY started_at DESC LIMIT 1                     │
│              Returns: latest collection run status and timestamp             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Layer Responsibilities

**Dashboard API Layer** (`app/api/v1/dashboard.py`): Validates query parameters via FastAPI's type system, enforces JWT authentication, instantiates `DashboardService`, calls one service method per endpoint (except `/organization` which calls five), constructs the typed response DTO from the dict returned by the service, and returns it. No SQL, no arithmetic, no string formatting logic.

**DashboardService** (`app/dashboard/service.py`): Orchestrates data retrieval by calling the appropriate EP-09 analytics service methods or repository methods, performs only non-business-logic composition (selecting max over a list, computing `avg = total / count` with zero-guard), and returns plain Python dicts. The `str()` Decimal conversion happens in the API layer, not here.

**AnalyticsService** (`app/analytics/service.py`, EP-09): Provides named methods with stable signatures for each analytics dimension. DashboardService calls these methods; it does not write SQL directly. This preserves the EP-09 analytics contract as an abstraction boundary.

**UsageCostRecordRepository** (`app/repositories/usage_cost_record_repository.py`, EP-09): Issues the actual SQL `SELECT ... GROUP BY ... ORDER BY` statements. Applies `deleted_at IS NULL` filters, soft-delete exclusion, and SQL `LIMIT` where applicable.

**Database** (PostgreSQL): `usage_cost_records` table with indexes on `(organization_id, usage_date)`. `usage_collection_runs` table queried directly by DashboardService for collection status.

### Package Structure

```
backend/
  app/
    dashboard/
      __init__.py          # Empty package marker (1 line)
      service.py           # DashboardService class — all orchestration logic
    api/v1/
      dashboard.py         # 7 FastAPI route handlers (F-060 through F-066)
    schemas/
      dashboard.py         # 9 Pydantic DTOs (OverviewResponse, TimeSeriesPoint, etc.)
  tests/
    test_ep10.py           # 78 hermetic unit/integration tests
  docs/
    knowledge/
      EP-10-Knowledge-Transfer.md     (this file)
      EP-10-Architecture-Review.md
      EP-10-Production-Readiness.md
    engineering/
      EP-10-Completion-Report.md
    architecture/
      ARCHITECTURE_CHANGELOG.md       (updated with [0.10.1] entry)
```

---

## Section 3 — Dashboard Endpoints

All endpoints are registered under the `APIRouter(prefix="/dashboard", tags=["dashboard"])` in `app/api/v1/dashboard.py` and then included via `api_router.include_router(dashboard.router, prefix="/v1")` in `app/api/router.py`, producing full paths at `/v1/dashboard/*`.

### F-060 — GET /v1/dashboard/overview

**Purpose:** Executive snapshot of an organization's total AI spend and operational status.

**Query Parameters:**
| Parameter | Type | Required | Default | Notes |
|-----------|------|----------|---------|-------|
| `organization_id` | UUID | Yes | — | Trusted from query string; membership not verified (EP-11) |
| `currency` | str | No | `"USD"` | Informational only — data currency is from cost records |

**Response Schema:** `OverviewResponse`
```
total_spend: str        # All-time total cost (Decimal as string)
today_spend: str        # Today's spend (UTC date)
month_spend: str        # Month-to-date spend
total_tokens: int       # All-time total tokens
total_requests: int     # All-time total request count
active_providers: int   # Count of distinct providers used all-time
active_models: int      # Count of distinct (provider, model) pairs used all-time
collection_status: str | None   # Last collection run status enum value (e.g. "completed")
last_collection_at: datetime | None  # Timestamp of last collection run
currency: str           # Currency parameter echoed back
```

**DashboardService calls:**
1. `_cost_repo().get_totals_by_org(org, date(2000,1,1), today)` — all-time totals
2. `_cost_repo().get_totals_by_org(org, month_start, today)` — MTD spend
3. `_cost_repo().get_totals_by_org(org, today, today)` — today's spend
4. `_cost_repo().get_totals_by_provider(org, date(2000,1,1), today)` — provider count
5. `_cost_repo().get_totals_by_model(org, date(2000,1,1), today)` — model count
6. Direct SQLAlchemy `select(UsageCollectionRun).order_by(desc(started_at)).limit(1)` — latest run

**Performance Note:** Six queries per call. Primary candidate for Redis caching at TTL 60–300s in EP-11+.

**Empty data handling:** When no cost records exist, all cost fields return `"0"`, counts return `0`, `collection_status` and `last_collection_at` return `None`.

---

### F-061 — GET /v1/dashboard/time-series

**Purpose:** Cost trend data bucketed by granularity for charting.

**Query Parameters:**
| Parameter | Type | Required | Default | Notes |
|-----------|------|----------|---------|-------|
| `organization_id` | UUID | Yes | — | |
| `start_date` | date | Yes | — | ISO 8601 (YYYY-MM-DD) |
| `end_date` | date | Yes | — | ISO 8601 (YYYY-MM-DD) |
| `granularity` | str | No | `"daily"` | One of: `daily`, `weekly`, `monthly` |
| `currency` | str | No | `"USD"` | |

**Response Schema:** `TimeSeriesResponse`
```
granularity: str
start_date: str          # ISO date string
end_date: str            # ISO date string
points: list[TimeSeriesPoint]   # Each point has: date, cost(str), tokens, requests, currency
total_cost: str          # Sum of all point costs
total_tokens: int        # Sum of all point tokens
total_requests: int      # Sum of all point requests
```

**DashboardService calls:** `_make_analytics_service().get_daily_trend(org, start_date, end_date)` — one query. Then Python-side grouping for weekly/monthly.

**Granularity behavior:**
- `daily`: ISO date string `"YYYY-MM-DD"` as key
- `weekly`: ISO week string `"YYYY-Www"` as key (e.g., `"2026-W26"`), using `date.isocalendar()`
- `monthly`: Year-month string `"YYYY-MM"` as key (e.g., `"2026-06"`)
- Unknown value: falls back to daily with a `structlog` warning — no 422 raised

**Empty data contract:** Returns 200 with `points: []` and `total_cost: "0"` — never 404.

---

### F-062 — GET /v1/dashboard/providers

**Purpose:** Cost breakdown by AI provider for a date range.

**Query Parameters:** `organization_id` (required), `start_date` (required), `end_date` (required), `currency` (optional, default `"USD"`)

**Response Schema:** `ProviderBreakdownResponse`
```
providers: list[ProviderMetrics]  # Each: provider, total_cost(str), total_tokens,
                                  #       total_requests, avg_cost_per_request(str), currency
total_cost: str          # Sum across all providers (computed at API layer)
period_start: str
period_end: str
```

**DashboardService calls:** `_make_analytics_service().get_provider_breakdown(...)` — one query.

**DashboardService computation:** `avg_cost_per_request = total_cost / record_count` with zero-guard (returns `Decimal(0)` when `record_count == 0`). This is the only arithmetic in EP-10 and it is a simple division with a guard, not business logic.

---

### F-063 — GET /v1/dashboard/models

**Purpose:** Cost breakdown by (provider, model) pair, sorted by cost descending, with SQL LIMIT.

**Query Parameters:** `organization_id`, `start_date`, `end_date`, `limit` (optional, default 20, ge=1, le=100), `currency`

**Response Schema:** `ModelBreakdownResponse`
```
models: list[ModelMetrics]   # Each: provider, model, total_cost(str), total_tokens,
                              #       total_requests, avg_cost_per_request(str), currency
total_cost: str              # Sum of listed models (not all models)
period_start: str
period_end: str
```

**DashboardService calls:** `_make_analytics_service().get_top_models(org, start, end, limit=limit)` — one query with SQL LIMIT applied in the repository (not Python-side slicing).

**Important:** `total_cost` in `ModelBreakdownResponse` sums only the listed (limited) models, not all models organization-wide. For org-wide totals, use `/overview` or `/organization`.

---

### F-064 — GET /v1/dashboard/organization

**Purpose:** Composite endpoint that fetches all dashboard data in a single HTTP call. Reduces client round-trips from 5 to 1 for the main dashboard page.

**Query Parameters:** `organization_id` (required), `start_date` (optional, defaults to first of current month), `end_date` (optional, defaults to today), `currency` (optional)

**Response:** `dict` (not a typed Pydantic model — intentional, see ADR-10-01)

```json
{
  "organization_id": "...",
  "period_start": "2026-06-01",
  "period_end": "2026-06-30",
  "currency": "USD",
  "overview": {
    "total_spend": "...", "today_spend": "...", "month_spend": "...",
    "total_tokens": 0, "total_requests": 0, "active_providers": 0,
    "active_models": 0, "collection_status": null, "last_collection_at": null
  },
  "provider_breakdown": [...],
  "top_models": [...],        // limit=5 (hardcoded, not the 20 default)
  "project_breakdown": [...],
  "daily_trend": [...]        // last 30 days (today - 29 days to today)
}
```

**DashboardService calls:** Five calls executed sequentially:
1. `svc.get_overview(org, today=today)` — 6 queries
2. `svc.get_provider_breakdown(org, start, end)` — 1 query
3. `svc.get_model_breakdown(org, start, end, limit=5)` — 1 query
4. `svc.get_project_breakdown(org, start, end)` — 1 query
5. `svc.get_time_series(org, today-29days, today, "daily")` — 1 query

Total: approximately 10 queries per call. Each query is independent (no N+1). Sequential execution is the current implementation; async parallelism is a known EP-11 optimization opportunity.

**Note:** `timedelta` import appears inside the endpoint function body — minor style issue (should be a module-level import, see REV-03 in Architecture Review).

---

### F-065 — GET /v1/dashboard/projects

**Purpose:** Cost breakdown grouped by project UUID (or `None` for unattributed costs).

**Query Parameters:** `organization_id`, `start_date`, `end_date`, `currency`

**Response Schema:** `ProjectBreakdownResponse`
```
projects: list[ProjectMetrics]  # Each: project_id(str|None), total_cost(str),
                                 #       total_tokens, total_requests, currency
total_cost: str
period_start: str
period_end: str
```

**Null project_id handling:** Costs not attributed to any project have `project_id: null` in the JSON response. This is correct — `None` is preserved through the DashboardService and DTO. The endpoint never coerces `None` to `"null"` or omits the field.

---

### F-066 — GET /v1/dashboard/kpis

**Purpose:** Derived key performance indicators — computed metrics that require cross-dimension analysis.

**Query Parameters:** `organization_id`, `start_date`, `end_date`, `currency`

**Response Schema:** `KPIResponse`
```
highest_cost_provider: str | None    # Provider with max total_cost in period
highest_cost_model: str | None       # Model with max total_cost in period
avg_cost_per_request: str | None     # total_cost / total_requests (Decimal as str)
avg_cost_per_token: str | None       # total_cost / total_tokens (Decimal as str)
period_start: str
period_end: str
currency: str
```

**DashboardService calls:**
1. `_make_analytics_service().get_provider_breakdown(...)` — for highest_cost_provider via `max(rows, key=lambda r: r["total_cost"])`
2. `_make_analytics_service().get_model_breakdown(...)` — for highest_cost_model
3. `_cost_repo().get_totals_by_org(...)` — for avg computations

**Null handling:** When no data exists, `highest_cost_provider`, `highest_cost_model`, `avg_cost_per_request`, and `avg_cost_per_token` are all `None`. The API layer correctly passes `None` through to the DTO without calling `str(None)`.

---

## Section 4 — DashboardService

### Design Principle

`DashboardService` (`app/dashboard/service.py`) is an orchestration-only class. Its docstring states explicitly: "Contains no business logic — all calculations are delegated to AnalyticsService and repositories." Every method calls one or more EP-09 methods, does minimal composition, and returns a plain Python dict for the endpoint to convert into a DTO.

### Constructor

```python
def __init__(self, session: AsyncSession) -> None:
    self._session = session
```

Accepts only the database session. No repositories or services are created at construction time — they are instantiated lazily inside methods.

### Lazy Import Pattern

Three private helper methods create dependencies on demand:

**`_make_analytics_service()`**: Creates `AnalyticsService(cost_record_repo=..., daily_summary_repo=...)` with lazy imports of both repository classes and the service itself. Called by `get_time_series`, `get_provider_breakdown`, `get_model_breakdown`, `get_project_breakdown`, and `get_kpis`.

**`_cost_repo()`**: Creates `UsageCostRecordRepository(self._session)` with a lazy import. Called directly by `get_overview` and `get_kpis` for org-level totals.

**`_run_repo()`**: Creates `UsageCollectionRunRepository(self._session)` with a lazy import. Instantiated in `get_overview` but the actual query is issued directly via `self._session.execute()` using a SQLAlchemy `select()` statement on `UsageCollectionRun`.

**Why lazy imports?** The circular import risk: `app/dashboard/service.py` → `app/analytics/service.py` → `app/repositories/...` → `app/models/...` → back potentially to dashboard if not careful. The lazy import pattern (imports inside method bodies using `TYPE_CHECKING` guard for type hints only) is consistent with the `UsageCollectionService` pattern from EP-08 and is explicitly noted in `app/dashboard/__init__.py`'s package context.

### Error Handling

`DashboardService` does not catch exceptions from its downstream calls. All database exceptions propagate to FastAPI's default exception handling, which returns HTTP 500 with appropriate error structure. The only explicit error handling is defensive programming: `or Decimal(0)` fallbacks when summing potentially empty lists, and `record_count > 0` guards before division.

### Logging

Uses `structlog.get_logger(__name__)` bound to the module. `get_overview()` logs one `INFO` event with `organization_id`, `total_cost`, `active_providers`, and `active_models`. `get_time_series()` logs a `WARNING` for unknown granularity values.

---

## Section 5 — Dashboard DTOs

All schemas are in `app/schemas/dashboard.py`. Every class uses `from __future__ import annotations` (file-level) and `model_config = ConfigDict(from_attributes=True)`.

### Why Decimal → str Serialization

JSON has no native decimal type. Python's `json.dumps()` converts `Decimal` to a string if using a custom encoder, or raises `TypeError` with the default encoder. FastAPI's Pydantic serialization of `Decimal` produces a JSON number (float-like string or numeric), which loses precision for values like `0.0000001234` (which IEEE 754 double cannot represent exactly).

The solution: declare all monetary fields as `str` in the schema. The endpoint function converts `Decimal` to `str` using Python's `Decimal.__str__()`, which produces the full decimal representation without scientific notation for normal values (e.g., `Decimal("100.00")` → `"100.00"`, `Decimal("0.00002000")` → `"0.00002000"`). This is lossless.

**Critical invariant tested in multiple places:** `isinstance(data["total_spend"], str)` — not `isinstance(data["total_spend"], (int, float))`.

### Schema Reference

| Schema | Used by | Key Fields |
|--------|---------|-----------|
| `OverviewResponse` | F-060 | `total_spend: str`, `today_spend: str`, `month_spend: str`, `collection_status: str \| None`, `last_collection_at: datetime \| None` |
| `TimeSeriesPoint` | F-061 | `date: str` (ISO or week or month key), `cost: str`, `tokens: int`, `requests: int` |
| `TimeSeriesResponse` | F-061 | `granularity: str`, `points: list[TimeSeriesPoint]`, `total_cost: str`, `total_tokens: int` |
| `ProviderMetrics` | F-062 | `provider: str`, `total_cost: str`, `avg_cost_per_request: str` |
| `ProviderBreakdownResponse` | F-062 | `providers: list[ProviderMetrics]`, `total_cost: str` |
| `ModelMetrics` | F-063 | `provider: str`, `model: str`, `total_cost: str`, `avg_cost_per_request: str` |
| `ModelBreakdownResponse` | F-063 | `models: list[ModelMetrics]`, `total_cost: str` |
| `ProjectMetrics` | F-065 | `project_id: str \| None`, `total_cost: str` |
| `ProjectBreakdownResponse` | F-065 | `projects: list[ProjectMetrics]`, `total_cost: str` |
| `KPIResponse` | F-066 | `highest_cost_provider: str \| None`, `avg_cost_per_request: str \| None`, `avg_cost_per_token: str \| None` |

### Forward Compatibility

`ConfigDict(from_attributes=True)` is set on every schema. While EP-10 never populates DTOs directly from ORM models (they are always built from dicts), this config allows future refactoring to pass ORM objects directly without changing the schema classes. It has no runtime cost when building from dicts.

### ORM Models Are Never Returned Directly

No endpoint ever serializes an ORM model object as a response. All responses are constructed from plain Python dicts returned by `DashboardService`. This ensures: (1) no accidental lazy-load triggers during serialization, (2) no ORM session lifetime dependency in the response path, and (3) exact control over which fields are exposed.

---

## Section 6 — Performance Strategy

### SQL LIMIT on Model Breakdown

The model breakdown endpoint (`/models`) applies `LIMIT` at the SQL level. The `limit` parameter flows from the API endpoint → `DashboardService.get_model_breakdown(limit=limit)` → `AnalyticsService.get_top_models(limit=limit)` → `UsageCostRecordRepository.get_totals_by_model(limit=limit)` where `stmt = stmt.limit(limit)` is applied before `execute()`. This was an EP-09 Release Hardening fix (RH-05) that corrected the prior Python-side slicing pattern.

Default limit: 20. Maximum: 100 (enforced by `Query(ge=1, le=100)` before the service is called).

### Use of Existing Aggregated Tables

All dashboard queries run against `usage_cost_records`, which has SQL-level aggregation via `GROUP BY ... ORDER BY ... LIMIT`. The `daily_cost_summaries` pre-aggregation table (built by `AggregationService`) is available but not yet used in EP-10 dashboard queries. This is intentional for EP-10's scope — the additional architectural complexity of choosing between live records and pre-aggregated summaries is deferred.

Future optimization path: replace `get_daily_trend()` calls (which scan `usage_cost_records`) with reads from `daily_cost_summaries` for large date ranges.

### No N+1 Queries

All aggregation is performed in a single SQL query per call to each repository method. The `get_overview()` method issues 6 queries (by design — 3 for different date ranges, 1 for providers, 1 for models, 1 for collection run), but each query aggregates across the full data set in SQL — there are no per-row secondary queries.

### Response Size Control

- `/models` endpoint: SQL LIMIT prevents returning hundreds of rows
- `/organization` endpoint: `top_models` is hardcoded at `limit=5`, `daily_trend` is hardcoded at last 30 days
- All other breakdown endpoints: no explicit result count limit (potential concern for very large organizations — see Architecture Review)

### Future Caching Targets

The `/overview` and `/organization` endpoints are prime Redis cache candidates because:
1. They issue the most database queries (6 and ~10 respectively)
2. Their inputs are bounded and deterministic (org_id + date)
3. Financial data can tolerate 60–300 seconds of staleness for dashboard display
4. Cache invalidation: purge by org_id when new usage collection runs complete

The time-series endpoint with wide date ranges is the next candidate.

---

## Section 7 — Security

### JWT Authentication

Every dashboard endpoint uses the `CurrentUser` dependency from `app/auth/dependencies.py`. This is declared via the `_user: CurrentUser` parameter on each handler function. FastAPI evaluates this dependency before executing the handler body. A missing or expired JWT returns 401 before any parameters are validated or any service code runs.

Implementation: `CurrentUser` is a FastAPI `Depends()` wrapper around the JWT validation function. Its return value (the current user object) is assigned to `_user` which is intentionally prefixed with `_` to indicate it is used for the side effect (auth enforcement) not its value.

### org_id as Query Parameter (Current Limitation)

`organization_id` is accepted as a query string parameter and trusted without verification. This means: any authenticated user who knows (or guesses) an organization UUID can query that organization's financial data. This is a known security limitation, explicitly documented in the endpoint module docstring:

```
# Authentication
# All endpoints require a valid JWT (CurrentUser). Org membership verification
# is deferred to EP-11 — for now we validate the JWT and trust the
# organization_id query parameter, matching the EP-09 pattern.
```

This is the same security posture as EP-09 analytics endpoints. It is acceptable for development and staging environments where a small team of trusted engineers is the user base.

### What EP-11 Must Implement

| Item | Current State | EP-11 Action |
|------|---------------|-------------|
| Org membership check | Not present | Verify authenticated user belongs to the requested org |
| RBAC `BILLING_READ` | Not present | Check permission before returning cost data |
| JWT-derived org_id | Query param (trusted) | Derive from JWT claims or verify against claims |
| Financial data access control | Any auth user sees any org | Restricted to org members with billing permission |

### Why Current State Is Acceptable for Dev/Staging

The production data risk is low in pre-production because: (1) no real billing decisions are made from the data, (2) the user base is the engineering team with shared context, and (3) the data at risk (AI spend totals) is less sensitive than the data EP-09 protects (which includes the same fields). The security posture matches EP-09 exactly and is explicitly inherited.

---

## Section 8 — API Design

### REST Conventions

All dashboard endpoints are read-only `GET` operations. Parameters are passed as query strings (no request bodies on GET). Route naming uses kebab-case (`/time-series`, not `/timeSeries` or `/time_series`). Resource naming is plural for collections (`/providers`, `/models`, `/projects`) and singular for singles or composites (`/overview`, `/organization`, `/kpis`).

### Date Range Validation

`start_date` and `end_date` are typed as `date` in FastAPI's `Query()` parameters. FastAPI parses ISO 8601 date strings (`YYYY-MM-DD`) and raises 422 for invalid formats before calling the handler. However, there is no validation that `start_date <= end_date` — a caller can provide `start_date > end_date` and receive an empty result set (no error). This is a known gap (see Architecture Review REV-02).

### Granularity Enum for Time Series

The `granularity` parameter on `/time-series` accepts any string (type annotation is `str`, not a Python `Literal` or `Enum`). Valid values are `"daily"`, `"weekly"`, `"monthly"`. An invalid value silently falls back to daily with a structlog warning — this is a silent degradation, not an error response (see Architecture Review REV-01).

### Empty List vs 404 Contract

A consistent design decision across all endpoints: when no data exists for a given organization and date range, the response is HTTP 200 with an empty list (or zero totals), never HTTP 404. Rationale: the organization exists, the API endpoint exists, the date range is valid — there is simply no data yet. A 404 would be misleading and would complicate client-side error handling (is this a missing resource or missing data?). Tests explicitly verify this contract: `test_time_series_empty_returns_200_not_404`, `test_providers_empty_returns_200_not_404`, etc.

### Status Codes

| Condition | HTTP Status |
|-----------|-------------|
| Successful response (including empty data) | 200 |
| Missing or invalid JWT | 401 |
| Missing required query parameter or type mismatch | 422 |
| `limit` out of range (< 1 or > 100) | 422 |
| Database error or unexpected exception | 500 |

### Consistent Query Parameter Naming

All endpoints use `organization_id` (not `org_id`, `orgId`, or `organization`). Date ranges use `start_date` and `end_date` (not `from`/`to` or `begin`/`finish`). These match the EP-09 analytics endpoint naming conventions for consistency.

---

## Section 9 — Testing Strategy

### Test Count: 78

Tests are organized in `tests/test_ep10.py` across 18 test classes covering schemas, service methods, auth guards, validation, happy paths, edge cases, and router registration.

| Test Class | Tests | Coverage |
|------------|-------|---------|
| `TestDashboardSchemas` | 13 | DTO construction, null fields, Decimal-as-string invariant verified on all schema types |
| `TestDashboardServiceOverview` | 5 | `get_overview()` return keys, no collection run, with collection run, empty cost data, provider count aggregation |
| `TestDashboardServiceTimeSeries` | 5 | Daily granularity, weekly grouping (two rows → one ISO week bucket), monthly grouping (two months → two buckets), empty → empty list, unknown granularity → daily fallback |
| `TestDashboardServiceProviderBreakdown` | 4 | Provider list, avg cost calculation (`80/8 = 10`), zero-division guard (`record_count=0`), empty → empty list |
| `TestDashboardServiceModelBreakdown` | 3 | Model list, limit forwarded to service (assertion on `get_top_models` call args), empty → empty list |
| `TestDashboardServiceProjectBreakdown` | 3 | Project list with UUID-to-str conversion, null project_id preserved, empty → empty list |
| `TestDashboardServiceKPIs` | 7 | All KPI keys present, highest-cost provider (multi-provider comparison), highest-cost model (multi-model), avg cost per request, avg cost per token, all None when no data, Decimal type assertion |
| `TestDashboardAuthGuards` | 7 | All 7 endpoints return 401 without JWT |
| `TestDashboardValidationGuards` | 3 | Missing org_id (401 or 422), missing org_id on time-series (401 or 422), invalid date format (401 or 422), `limit=200` returns 422 |
| `TestOverviewEndpoint` | 3 | 200 with auth, response shape (all keys present), Decimal fields are JSON strings |
| `TestTimeSeriesEndpoint` | 5 | Daily 200, weekly 200, monthly 200, empty → 200 with `points: []`, `total_cost` is string |
| `TestProviderEndpoint` | 2 | 200 with providers list, empty → 200 with `providers: []` |
| `TestModelsEndpoint` | 3 | 200 with models list, `limit=5` accepted, empty → 200 with `models: []` |
| `TestOrganizationEndpoint` | 3 | 200 with all composite keys, full structure validation (overview block has string spend fields), optional date params default correctly |
| `TestProjectsEndpoint` | 2 | 200 with projects list, empty → 200 with `projects: []` |
| `TestKPIsEndpoint` | 3 | 200 with all KPI keys, empty → 200 with nulls, avg fields are strings or null |
| `TestDecimalSerializationInAPI` | 3 | `total_cost` is string in providers, models, and projects responses |
| `TestRouterRegistration` | 2 | All 7 `/v1/dashboard/*` paths in OpenAPI spec, `"dashboard"` tag present in spec |

### Mock Strategy

**Service unit tests:** Use `unittest.mock.patch()` to replace `DashboardService._cost_repo`, `DashboardService._run_repo`, and `DashboardService._make_analytics_service` with `AsyncMock` instances. This tests the service's orchestration logic (e.g., correct method called with correct arguments, correct computation of avg, correct bucketing) without touching the database.

**API tests:** Use FastAPI's `dependency_overrides` to replace `get_current_user` (JWT bypassed) and `get_db` (yields an `AsyncMock` session). The `AsyncMock` session's `execute()` method returns a `MagicMock` with `scalar_one_or_none()` and `all()` configured to return empty results. This means all API tests run DashboardService real code but with a mocked database — the actual SQL is not issued.

**Why the DB is not mocked at the service boundary for API tests:** The API tests verify the full response shape including Decimal serialization and status codes. Running the actual DashboardService (with a mocked DB returning empty results) validates the full response construction path.

### Decimal-as-String Assertion Pattern

Tests assert `isinstance(data["total_cost"], str)` on JSON responses, not `isinstance(data["total_cost"], float)`. This verifies the critical invariant: monetary values must be JSON strings. The JSON response body is parsed with `resp.json()`, and Python's `json.loads()` would return a `float` if FastAPI serialized a Decimal as a number — the test would catch this.

---

## Section 10 — Future React Dashboard

### Endpoint-to-Component Mapping

Each EP-10 endpoint is designed to feed a specific React component type in the planned executive dashboard UI:

| Endpoint | React Component | UI Purpose |
|----------|----------------|-----------|
| `/overview` | KPI card grid | Four cards: Total Spend, Today's Spend, MTD Spend, Active Models/Providers |
| `/time-series` (daily) | Line/area chart | 30-day cost trend with day-by-day data points |
| `/time-series` (weekly) | Bar chart | Week-over-week cost comparison |
| `/time-series` (monthly) | Bar chart or table | Month-over-month cost trend |
| `/providers` | Horizontal bar chart | Provider cost comparison with percentage share |
| `/models` | Sortable table | Model efficiency table — cost, tokens, avg per request |
| `/projects` | Pie chart or table | Project spend attribution |
| `/kpis` | Headline metric row | "Top Provider: OpenAI ($X), Avg per Request: $Y" |
| `/organization` | Full dashboard page | One call loads all components simultaneously |

### Why `/organization` Is the Dashboard Page Endpoint

The `/organization` endpoint exists precisely for the dashboard page load. A React component mounting the main dashboard would need: overview KPIs, a provider chart, a top models list, a project breakdown, and a cost trend chart. Without `/organization`, the React app would make 5 separate API calls on mount, each returning before the others, causing staggered loading states. With `/organization`, a single call returns all data at once, enabling a clean single loading state.

### What EP-11 Must Add for the React Dashboard

1. **Authentication context**: The React app must send a JWT bearer token. EP-11 will add org membership to JWT claims so the frontend does not need to supply `organization_id` separately.
2. **RBAC permission**: The `BILLING_READ` permission must be checked before returning financial data.
3. **Org-ID from JWT**: The API should derive the org from the authenticated user's JWT rather than accepting an arbitrary UUID from the query string.
4. **Response caching headers**: `Cache-Control`, `ETag` or `Last-Modified` for browser-level caching.
5. **WebSocket or SSE**: For real-time cost updates during active collection runs (long-term).

---

## Section 11 — Top 40 Engineering Concepts

1. **Orchestration Layer Pattern**: `DashboardService` composes responses from existing EP-09 services without adding new business logic. The service's value is composition and delegation, not computation.

2. **Thin Controller Pattern**: API endpoint functions contain only: parameter validation (handled by FastAPI), service instantiation (`DashboardService(session=db)`), one service call, and DTO construction. No arithmetic, no conditionals on data values, no string formatting except for Decimal→str conversion.

3. **Decimal-as-String Serialization**: All monetary Pydantic fields typed as `str`. The `str(Decimal_value)` call at the API layer converts the Decimal to its string representation losslessly, preventing JSON float precision loss.

4. **Lazy Dependency Instantiation**: Repositories and services are constructed inside service methods via `_make_analytics_service()`, `_cost_repo()`, and `_run_repo()` helper methods. This avoids circular imports and follows the pattern established in EP-08 (`UsageCollectionService`) and EP-09.

5. **ISO Week Grouping with `isocalendar()`**: Weekly time-series keys use Python's `date.isocalendar()` which returns a named tuple with `.year` and `.week`. Key format is `f"{iso.year}-W{iso.week:02d}"` (e.g., `"2026-W26"`). This is correct ISO 8601 week notation.

6. **SQL LIMIT at Repository Layer**: The `limit` parameter flows from the API endpoint to `get_top_models(limit=limit)` in the repository, where `stmt = stmt.limit(limit)` is applied before `execute()`. No Python-side slicing — resolves EP-09's REV-07 finding.

7. **JWT-First Authentication**: FastAPI evaluates the `CurrentUser` dependency before the endpoint body. An invalid JWT returns 401 before query parameters are validated. This is why some validation tests accept either 401 or 422.

8. **Composite Endpoint Pattern** (`/organization`): A single endpoint that calls multiple service methods and composes a unified response. Reduces React dashboard page-load from 5 round-trips to 1. The endpoint issues ~10 database queries sequentially — parallel execution is a known EP-11 optimization.

9. **Empty-200 Contract**: Every list endpoint returns HTTP 200 with an empty list when no data exists. This is documented, tested with `test_*_empty_returns_200_not_404` tests, and consistent with the EP-09 analytics pattern.

10. **UTC-Safe Date Derivation**: `datetime.now(tz=UTC).date()` is used for the default `today` date in `get_overview()` and `get_organization_dashboard()`. Prevents off-by-one errors when the server clock is in a non-UTC timezone (resolves EP-09 REV-04).

11. **Sentinel Date for All-Time Queries**: `date(2000, 1, 1)` is used as the start sentinel for "all-time" cost queries in `get_overview()`. Safe because AI usage data does not predate the system deployment. Avoids requiring a min-date schema field.

12. **Division-by-Zero Guard in DashboardService**: Provider breakdown and KPI methods use `if record_count > 0: avg = total / count else: avg = Decimal(0)`. Similarly for `avg_cost_per_token`: `if total_tokens > 0: avg = total / Decimal(total_tokens) else: avg = None`. The choice of `Decimal(0)` vs `None` differs between methods based on semantic meaning.

13. **`from __future__ import annotations`**: Present on all EP-10 production files (`service.py`, `dashboard.py`, `schemas/dashboard.py`) and test file. Enables PEP 563 postponed evaluation of annotations — allows `date | None` syntax without Python 3.10+ requirement.

14. **FastAPI Router Prefix Convention**: `APIRouter(prefix="/dashboard", tags=["dashboard"])` in `dashboard.py`, then `api_router.include_router(dashboard.router, prefix="/v1")` in `router.py`. This double-prefix pattern produces `/v1/dashboard/*` and is consistent across all EP-07 through EP-10 endpoints.

15. **`DbDep` Type Alias**: `DbDep = Annotated[AsyncSession, Depends(get_db)]` defined in `app/api/deps.py` and used in every endpoint signature. Reduces boilerplate and ensures consistent session injection behavior (commit on success, rollback on exception).

16. **`response_model` Enforcement**: FastAPI's `response_model=OverviewResponse` (etc.) on each endpoint validates the response at runtime in development mode and generates accurate OpenAPI documentation. The `/organization` composite endpoint uses `-> dict` without `response_model` — a known gap (see Architecture Review REV-04).

17. **`Field(default_factory=list)` for Collection Fields**: `TimeSeriesResponse.points`, `ProviderBreakdownResponse.providers`, etc. use `Field(default_factory=list)` to ensure the default value is a new empty list (not a shared mutable default). Prevents the Python mutable-default-argument bug at the Pydantic level.

18. **`ConfigDict(from_attributes=True)`**: Present on all 9 DTO schemas. Enables ORM-to-Pydantic construction via `Model.model_validate(orm_obj)` — not used in EP-10 but set for forward compatibility.

19. **`AsyncMock` Test Pattern**: Tests use `unittest.mock.AsyncMock` for all `async def` methods that need to be mocked. Using a regular `MagicMock` for an async method would cause `TypeError: object is not awaitable`. The `_make_analytics_service_mock()` and `_make_cost_repo_mock()` helper functions in the test file centralize this construction.

20. **`structlog` in Service Layer**: `log = structlog.get_logger(__name__)` at module level. Log events use named keyword arguments (`organization_id=str(organization_id)`) — never f-string interpolation. The `str()` conversion on UUIDs prevents structlog from serializing UUID objects differently across environments.

21. **Pydantic Schema Not Populating from Repository Rows**: The EP-09 analytics layer returns `list[dict]` from all repository methods. DashboardService reshapes these dicts and the API layer constructs DTOs from explicit keyword arguments. This avoids Pydantic field name collision issues between the repository dict keys and the DTO field names.

22. **Monthly Granularity Key Format**: Monthly buckets use `f"{d.year}-{d.month:02d}"` (zero-padded month) producing `"2026-06"`, not `"2026-6"`. Zero-padding ensures lexicographic sort equals chronological sort, which matters for React charting libraries.

23. **`_user` Naming Convention for Auth Dependency**: The `CurrentUser` dependency is assigned to `_user` (underscore-prefixed) in every endpoint signature. This Python convention signals "used for side effects only" (authentication enforcement) and suppresses linter warnings about unused variables.

24. **`Annotated[type, Query(...)]` Pattern**: FastAPI query parameters are typed using `Annotated[uuid.UUID, Query(description="...")]`. This keeps the type system clean while attaching FastAPI metadata for OpenAPI documentation and validation constraint enforcement (e.g., `ge=1, le=100` on `limit`).

25. **`_DEFAULT_CURRENCY = "USD"` Module Constant**: Used in `DashboardService` for the KPI and overview response `currency` field. A module-level constant ensures consistent currency labeling without magic strings in method bodies.

26. **`r.get("currency", currency)` Fallback**: In API endpoints, rows returned by DashboardService use `.get("currency", currency)` to fall back to the request's `currency` parameter if the row doesn't include a currency key. This is defensive coding against future schema changes.

27. **`sum((x for x in rows), Decimal(0))` Pattern**: The API layer computes `total_cost` for breakdown responses using generator-based `sum()` with `Decimal(0)` as the start value. This avoids the `sum([Decimal values], start)` pitfall where Python defaults to integer `0`, which would cause a type mismatch on the first addition.

28. **`scalar_one_or_none()` for Single-Row Queries**: The collection run query uses `result.scalar_one_or_none()` which returns the ORM object or `None` cleanly. No iteration, no index access, no `fetchone()` pattern.

29. **`desc()` Import for Collection Run Query**: `from sqlalchemy import and_, desc, select` at the top of `service.py`. The `desc()` function is used in the collection run ORDER BY clause: `.order_by(desc(UsageCollectionRun.started_at))`.

30. **Weekly Bucketing with `dict` (Ordered by Insertion)**: The weekly grouping in `get_time_series()` uses a plain `dict` (`buckets: dict[str, dict] = {}`). Since Python 3.7+, dict preserves insertion order. Because daily data is returned in date order from the SQL query (`.order_by(usage_date.asc())`), the weekly buckets are naturally in chronological order by first occurrence.

31. **Composite Response Without `response_model`**: The `/organization` endpoint uses `-> dict` with no `response_model`. This avoids the overhead of defining a composite Pydantic schema with deeply nested fields, at the cost of runtime validation. Decimal serialization in the composite response is handled by explicit `str()` calls throughout the dict construction.

32. **`timedelta` Import Inside Endpoint Body**: In `get_organization_dashboard()`, `from datetime import timedelta` is imported inside the function body at line 249. This is a style inconsistency — it should be a module-level import. The code works correctly but is flagged as REV-03 in the Architecture Review.

33. **No Service Constructor Wiring**: Unlike some service patterns where all dependencies are passed to `__init__`, `DashboardService` defers dependency creation. This simplifies the caller (`DashboardService(session=db)` — one argument) and makes the service testable without providing fake repos to the constructor.

34. **Test `_make_dashboard_service()` Helper**: The test file defines a `_make_dashboard_service()` helper that creates a `DashboardService` with a mock session. This avoids repeating mock setup across dozens of tests and ensures all service tests use the same mock construction pattern.

35. **Endpoint-Level Auth Override in Tests**: API tests use `app.dependency_overrides[get_current_user] = mock_get_user` and `app.dependency_overrides[get_db] = mock_get_db`. These overrides are set in a `try/finally` block to ensure `app.dependency_overrides.clear()` always runs, preventing test contamination.

36. **`_DAILY_TREND_ROW` Missing `total_tokens` Key**: In the test file, `_DAILY_TREND_ROW` uses the key `"total_tokens"` (line 88: `"total_tokens": 500`) but the `get_time_series()` method in DashboardService reads `r["total_tokens"]` from AnalyticsService rows. The AnalyticsService mock returns `_DAILY_TREND_ROW` which has this key. This is consistent and correct.

37. **KPI `get_model_breakdown` vs `get_top_models`**: In `DashboardService.get_kpis()`, the call for highest-cost model uses `svc.get_model_breakdown()` (line 327), while the test's `_make_analytics_service_mock()` wires `svc.get_model_breakdown` to return `model_rows`. However, `DashboardService.get_model_breakdown()` (the method on DashboardService itself) calls `svc.get_top_models()`. In `get_kpis()`, DashboardService calls `AnalyticsService.get_model_breakdown()` directly (not its own `get_model_breakdown` method). This is a subtle distinction — DashboardService.get_kpis() calls `AnalyticsService.get_model_breakdown()` (no limit), while DashboardService.get_model_breakdown() calls `AnalyticsService.get_top_models()` (with limit).

38. **`ge=1, le=100` Constraint on `limit`**: The `limit` parameter on `/models` uses `Query(description="Maximum models to return", ge=1, le=100)`. FastAPI validates this before calling the handler — `limit=0` or `limit=200` returns 422. The test `test_models_limit_exceeds_max` verifies this.

39. **Router Tag Verified in OpenAPI**: `TestRouterRegistration.test_dashboard_tags_in_openapi` fetches `/openapi.json` and asserts `"dashboard"` appears in the `tags` of at least one path operation. This verifies the `tags=["dashboard"]` on the router is propagated correctly to the OpenAPI spec.

40. **Zero New Migrations**: EP-10 introduces no new database tables, columns, indexes, or constraints. All data is read from tables created in EP-09 (`usage_cost_records`, `daily_cost_summaries`, `usage_collection_runs`). This means EP-10 can be deployed and rolled back without any database schema changes.
