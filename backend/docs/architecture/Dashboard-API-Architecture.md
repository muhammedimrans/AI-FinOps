# Dashboard API Architecture

**EP-10 — Dashboard API & Executive Analytics Layer**
**Date:** 2026-06-30

---

## Overview

The Dashboard API is a read-only analytics interface that composes cost and usage data for executive-level consumption. It sits atop the Cost & Analytics Engine (EP-09) and delegates all data access to existing services and repositories.

---

## System Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                         HTTP Clients                                  │
│          (Browser Dashboard, CLI, Reporting Tools)                   │
└─────────────────────────────┬────────────────────────────────────────┘
                              │ HTTPS / JWT Bearer
                              ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    FastAPI Application                                │
│  ┌────────────────────────────────────────────────────────────────┐  │
│  │                  Dashboard Router                              │  │
│  │  GET /v1/dashboard/overview        (F-060)                    │  │
│  │  GET /v1/dashboard/time-series     (F-061)                    │  │
│  │  GET /v1/dashboard/providers       (F-062)                    │  │
│  │  GET /v1/dashboard/models          (F-063)                    │  │
│  │  GET /v1/dashboard/organization    (F-064)                    │  │
│  │  GET /v1/dashboard/projects        (F-065)                    │  │
│  │  GET /v1/dashboard/kpis            (F-066)                    │  │
│  └──────────────────────────┬─────────────────────────────────────┘  │
│                             │                                        │
│  ┌──────────────────────────▼─────────────────────────────────────┐  │
│  │              DashboardService (orchestration)                  │  │
│  │  - get_overview()           - get_kpis()                      │  │
│  │  - get_time_series()        - get_project_breakdown()         │  │
│  │  - get_provider_breakdown() - get_model_breakdown()           │  │
│  └────────────┬──────────────────────────┬────────────────────────┘  │
│               │                          │                           │
│  ┌────────────▼────────────┐  ┌──────────▼──────────────────────┐  │
│  │    AnalyticsService     │  │  UsageCostRecordRepository      │  │
│  │    (EP-09)              │  │  (EP-09)                        │  │
│  │  get_provider_          │  │  get_totals_by_org()            │  │
│  │    breakdown()          │  │  get_daily_trend()              │  │
│  │  get_model_             │  │                                 │  │
│  │    breakdown()          │  └──────────────────────────────────┘  │
│  │  get_top_models()       │                                        │
│  │  get_daily_trend()      │                                        │
│  └─────────────────────────┘                                        │
└──────────────────────────────────────────────────────────────────────┘
                              │
                              ▼ SQLAlchemy AsyncSession
┌──────────────────────────────────────────────────────────────────────┐
│                         PostgreSQL                                    │
│  ┌─────────────────────────┐   ┌──────────────────────────────────┐  │
│  │   usage_cost_records    │   │   daily_cost_summaries           │  │
│  │   (primary source)      │   │   (future optimization target)   │  │
│  └─────────────────────────┘   └──────────────────────────────────┘  │
│  ┌─────────────────────────┐   ┌──────────────────────────────────┐  │
│  │   usage_collection_runs │   │   model_pricing                  │  │
│  │   (status for overview) │   │   (EP-09, not queried here)      │  │
│  └─────────────────────────┘   └──────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Request / Response Flow

```
Client
  │
  │  GET /v1/dashboard/overview
  │  Authorization: Bearer <jwt>
  │
  ▼
FastAPI Router (app/api/v1/dashboard.py)
  │
  ├─ [1] Dependency injection: get_db() → AsyncSession
  ├─ [2] Auth check: CurrentUser (JWT decode + user lookup)
  ├─ [3] Parameter validation: organization_id (UUID)
  │
  ▼
DashboardService(session=db)
  │
  ├─ [4]  cost_repo.get_totals_by_org(org, 2000-01-01, today)  → all-time totals
  ├─ [5]  cost_repo.get_totals_by_org(org, month_start, today) → MTD totals
  ├─ [6]  cost_repo.get_totals_by_org(org, today, today)       → today totals
  ├─ [7]  cost_repo.get_totals_by_provider(org, ...)           → provider set
  ├─ [8]  cost_repo.get_totals_by_model(org, ...)              → model set
  ├─ [9]  SELECT UsageCollectionRun WHERE org ORDER BY started_at DESC LIMIT 1
  │
  └─ returns dict with all overview fields
  │
  ▼
Endpoint function (app/api/v1/dashboard.py)
  │
  ├─ Constructs OverviewResponse DTO
  ├─ Serializes all Decimal fields as str()
  │
  ▼
FastAPI JSON serialization → 200 OK
```

---

## Service Composition Pattern

`DashboardService` follows the **Service Facade** pattern: it exposes a simplified interface (one method per dashboard view) that orchestrates multiple underlying calls. Consumers do not need to know which repositories or sub-services are involved.

```python
class DashboardService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _make_analytics_service(self):
        # Lazy instantiation — avoids circular imports
        from app.analytics.service import AnalyticsService
        from app.repositories.usage_cost_record_repository import UsageCostRecordRepository
        from app.repositories.daily_cost_summary_repository import DailyCostSummaryRepository
        return AnalyticsService(
            cost_record_repo=UsageCostRecordRepository(self._session),
            daily_summary_repo=DailyCostSummaryRepository(self._session),
        )
```

This pattern was established in EP-08/09 and is followed consistently.

---

## DTO Boundary

ORM models (SQLAlchemy `BaseModel` subclasses) are **never returned directly from endpoints**. The conversion happens in two stages:

```
ORM Model (SQLAlchemy)
      │
      │ Repository aggregation query
      ▼
dict (row data with Decimal values)
      │
      │ DashboardService composition
      ▼
dict (composed response dict)
      │
      │ Endpoint function — explicit DTO construction
      ▼
Pydantic Schema (str fields for all Decimal values)
      │
      │ FastAPI JSON serialization
      ▼
JSON Response ({"total_spend": "100.00", ...})
```

**Why this matters:** Converting at the DTO boundary means:
1. No ORM session leakage into the response layer
2. Decimal precision is preserved (strings, not floats)
3. The API contract is explicit and testable independent of the ORM

---

## Security Boundaries

### EP-10 State

```
Request
  │
  ▼
JWT Validation (required — returns 401 on failure)
  │
  ▼
Endpoint Logic (trusts organization_id from query param)
  │
  ▼
Cost Records (filtered by organization_id in WHERE clause)
```

The `organization_id` WHERE clause in all queries ensures that data from other organizations is never included in the response, even if a caller passes a different org's ID. However, a malicious authenticated user can query another org's data by passing that org's ID.

### EP-11 Target State

```
Request
  │
  ▼
JWT Validation (required)
  │
  ▼
Org Membership Check (user must be member of requested org)
  │
  ▼
RBAC Check (user must have BILLING_READ permission)
  │
  ▼
Endpoint Logic
```

---

## Performance Considerations

### Current Query Profile

All queries use indexes on `(organization_id, usage_date)` on `usage_cost_records`. For typical organizations with months of data, queries complete in single-digit milliseconds.

### The `/organization` Composite Endpoint

The composite endpoint (`F-064`) issues up to 9 DB queries. For the MVP this is acceptable. At scale, two strategies can reduce this:

1. **Redis caching**: Cache the composite response with `TTL=300s` keyed on `(org_id, start_date, end_date)`. Invalidate on new cost record write.
2. **Single aggregation query**: Replace multiple calls with a single CTE-based query that produces all dimensions at once.

### `DailyCostSummary` as Future Optimization

EP-09 builds `DailyCostSummary` records via `AggregationService`. EP-10 does not currently use them — all queries go to `usage_cost_records`. A future optimization would replace the trend and breakdown queries with pre-aggregated summary queries, reducing query cost by 10-100x for large orgs.

### Caching Readiness

Endpoints suitable for caching:

| Endpoint | Cache Key | TTL |
|----------|-----------|-----|
| `/overview` | `(org_id, today)` | 5 min |
| `/organization` | `(org_id, start, end)` | 5 min |
| `/time-series` | `(org_id, start, end, granularity)` | 5 min |
| `/providers` | `(org_id, start, end)` | 5 min |
| `/models` | `(org_id, start, end, limit)` | 5 min |

Cache invalidation trigger: any new `UsageCostRecord` write for the organization.
