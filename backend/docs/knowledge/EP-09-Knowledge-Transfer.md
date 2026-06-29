# EP-09 Knowledge Transfer: Cost & Analytics Engine

**Epic:** EP-09  
**Feature:** Cost & Analytics Engine  
**Status:** Complete  
**Date:** 2026-06-29  
**Author:** Implementation Team

---

## 1. Overview

EP-09 implements the Cost & Analytics Engine for AI FinOps. It introduces three new
database tables (`model_pricing`, `usage_cost_records`, `daily_cost_summaries`), a
deterministic pricing engine, a read-only analytics service, an aggregation service
for pre-computing daily summaries, and REST API endpoints for pricing management and
analytics queries.

### Key Features Implemented

| Feature | Code | Description |
|---------|------|-------------|
| F-051 | `PricingEngine` | Deterministic cost calculation from token counts |
| F-051 | `ModelPricing` | Versioned pricing config per (provider, model) |
| F-051 | `UsageCostRecord` | One cost record per usage event |
| F-053 | `AnalyticsService` | Read-only analytics queries |
| F-054 | `DailyCostSummary` | Pre-aggregated daily totals |
| F-054 | `AggregationService` | Builds/rebuilds daily summaries |
| F-056 | `PricingValidator` | Validates pricing configs before persistence |

---

## 2. Pricing Lifecycle

Pricing records follow a versioned lifecycle:

```
CREATE pricing v1 (effective_from: 2024-01-01, effective_to: NULL)
    → pricing v1 is "currently active" (effective_to IS NULL)

UPDATE: set v1 effective_to = 2024-12-31
CREATE pricing v2 (effective_from: 2025-01-01, effective_to: NULL)
    → v2 is now the active version
    → v1 is a historical record

LOOKUP for date 2024-06-15: returns v1
LOOKUP for date 2025-03-01: returns v2
```

**Key invariant:** Only one pricing version should be active for any given date. The
`PricingValidator.validate_no_overlap()` method enforces this before persistence.

---

## 3. Historical Pricing Resolution Algorithm

`ModelPricingRepository.get_for_date(provider, model, usage_date)` resolves pricing
using this SQL predicate:

```sql
WHERE provider = :provider
  AND model = :model
  AND is_active = TRUE
  AND deleted_at IS NULL
  AND effective_from <= :usage_date
  AND (effective_to IS NULL OR effective_to >= :usage_date)
ORDER BY effective_from DESC
LIMIT 1
```

The `ORDER BY effective_from DESC` ensures the most recently effective version is
returned when multiple versions match (which should not happen if overlap validation
is properly enforced).

---

## 4. Decimal Precision Strategy

**All monetary values use `decimal.Decimal` — never `float`.**

- Price-per-token storage: `Numeric(20, 10)` — supports prices as small as 10^-10
- Computed cost storage: `Numeric(20, 8)` — computed values at 8dp precision
- All calculations use `ROUND_HALF_UP` quantized to `Decimal("0.00000001")` (8dp)
- API responses serialize Decimal as strings to prevent JSON float precision loss

```python
_QUANT = Decimal("0.00000001")
prompt_cost = (Decimal(prompt_tokens) * pricing.prompt_token_price).quantize(
    _QUANT, rounding=ROUND_HALF_UP
)
```

Why `ROUND_HALF_UP`? Financial calculations conventionally use this rounding mode to
minimize cumulative bias. Python's default `ROUND_HALF_EVEN` (banker's rounding) is
preferred for statistical work but non-intuitive for billing.

---

## 5. Cost Attribution Model

Cost records are linked to the original `UsageEvent` via a 1:1 FK relationship:

```
UsageEvent (1) ──→ (0..1) UsageCostRecord
```

Each `UsageCostRecord` denormalizes key fields from the event (`provider`, `model`,
`usage_date`) to enable efficient analytics queries without joins. The `usage_date`
field is extracted from the event's `timestamp` at record creation time.

The `model_pricing_id` FK links to the specific pricing version used, supporting
audit trails and cost recalculation when pricing changes.

---

## 6. Analytics Architecture

```
UsageCostRecord (detailed)
    ↓ raw queries          ↓ aggregation
                      DailyCostSummary (pre-aggregated)
                              ↓
                       AnalyticsService
                              ↓
                       Analytics API
```

`AnalyticsService` reads from `UsageCostRecord` for detailed breakdowns. The
`DailyCostSummary` table is maintained by `AggregationService` for fast date-range
queries but is not the primary source for the EP-09 analytics endpoints.

---

## 7. Aggregation Strategy

`AggregationService.build_daily_summaries(org_id, date)` runs a SQL GROUP BY
query on `UsageCostRecord` grouped by `(organization_id, project_id, provider, model,
currency)` and upserts the results into `DailyCostSummary` using PostgreSQL
`ON CONFLICT DO UPDATE`.

`AggregationService.rebuild_range(org_id, start_date, end_date)` iterates day by
day, calling `build_daily_summaries` for each. This is suitable for:
- Backfilling historical data after pricing changes
- Nightly batch runs to keep summaries current
- On-demand refresh after bulk cost recalculation

---

## 8. API Design

### Pricing Endpoints (`/v1/pricing/`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/pricing/calculate` | Calculate cost for token counts |
| GET | `/v1/pricing/models` | List model pricing records |
| GET | `/v1/pricing/providers` | List providers with active pricing |
| POST | `/v1/pricing/models` | Create a new pricing record |

### Analytics Endpoints (`/v1/analytics/`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/analytics/usage` | Usage summary (tokens, requests) |
| GET | `/v1/analytics/cost` | Cost summary (total cost) |
| GET | `/v1/analytics/providers` | Per-provider cost breakdown |
| GET | `/v1/analytics/models` | Per-model cost breakdown |
| GET | `/v1/analytics/projects` | Per-project cost breakdown |
| GET | `/v1/analytics/organizations/{org_id}/summary` | Combined org summary |

All endpoints return Decimal values as strings in JSON responses.

---

## 9. RBAC Integration

EP-09 endpoints require a valid JWT (`CurrentUser`). Full RBAC enforcement
(org membership verification, `BILLING_READ`/`BILLING_WRITE`/`USAGE_READ`
permissions) is deferred to EP-10.

In production, the analytics and pricing endpoints should:
1. Validate JWT and extract `user_id`
2. Resolve `organization_id` to verify the user is a member
3. Check the user's role has the required permission
4. Apply tenant isolation (add `WHERE organization_id = :org_id` to all queries)

---

## 10. EP-10 Prerequisites

The following work is deferred to EP-10:

1. **Full RBAC enforcement**: Wire `RequirePermission(Permission.BILLING_READ)` and
   `RequirePermission(Permission.USAGE_READ)` once analytics endpoints support `org_id`
   as a path parameter (or add custom org-from-query-param resolution).

2. **JWT org binding**: Derive `organization_id` from JWT claims rather than accepting
   it as a query parameter. This closes a tenant isolation gap.

3. **Cost record population**: The `UsageCostRecord` table exists but is empty until
   EP-10 wires the `PricingEngine` into the usage collection pipeline.

4. **Daily summary scheduling**: `AggregationService.rebuild_range` should be called
   by a scheduled job (e.g., nightly cron) to keep summaries current.

5. **Pricing cascade recalculation**: When pricing is updated, cost records computed
   with the old pricing should be recalculated. EP-10 should implement a background
   job for this.

6. **Budget alerts and forecasting**: Not implemented in EP-09. Planned for EP-10+.

---

## 11. Data Flow Diagram

```
Provider API
    ↓
UsageEvent (via EP-08 collection pipeline)
    ↓
PricingEngine.calculate_event_cost()
    ↓ resolves ModelPricing for (provider, model, date)
    ↓ computes costs in Decimal
UsageCostRecord (1:1 with UsageEvent)
    ↓
AggregationService.build_daily_summaries()
    ↓
DailyCostSummary (pre-aggregated)
    ↓
AnalyticsService → Analytics API → Client
```

---

## 12. Testing Strategy

All EP-09 tests are hermetic — no live DB or network required. The test file
`tests/test_ep09.py` covers:

- Model field types (Decimal, date, UUID)
- Repository mock-session patterns
- PricingEngine: `calculate_cost` precision, ROUND_HALF_UP, `PricingNotFoundError`
- PricingValidator: all validation rules, overlap detection
- AnalyticsService: all query methods with mock repos
- AggregationService: summary building with empty and populated result sets
- API endpoints: 401 auth guard, mocked DB responses, schema serialization

**Test count:** 135 tests in `tests/test_ep09.py`

---

## 13. Files Created

### Models
- `app/models/model_pricing.py`
- `app/models/usage_cost_record.py`
- `app/models/daily_cost_summary.py`

### Repositories
- `app/repositories/model_pricing_repository.py`
- `app/repositories/usage_cost_record_repository.py`
- `app/repositories/daily_cost_summary_repository.py`

### Pricing Package
- `app/pricing/__init__.py`
- `app/pricing/engine.py`
- `app/pricing/validator.py`

### Analytics Package
- `app/analytics/__init__.py`
- `app/analytics/service.py`
- `app/analytics/aggregation.py`

### Schemas
- `app/schemas/pricing.py`
- `app/schemas/analytics.py`

### API
- `app/api/v1/pricing.py`
- `app/api/v1/analytics.py`

### Migration
- `migrations/versions/20260629_0900_f7a8b9c0d1e2_ep09_cost_analytics.py`

### Modified Files
- `app/models/__init__.py` (added EP-09 imports)
- `app/api/router.py` (added pricing and analytics routers)
