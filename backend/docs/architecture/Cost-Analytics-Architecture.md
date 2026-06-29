# Cost & Analytics Architecture (EP-09)

**Version:** 1.0  
**Date:** 2026-06-29

---

## 1. Overview

The Cost & Analytics Engine calculates AI API costs from usage events and exposes
analytics queries via REST API. It is built on three new database tables and two
new Python packages.

---

## 2. Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           EP-09 DATA FLOW                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  Provider API                                                                 │
│      │                                                                        │
│      ▼ (EP-08 collection pipeline)                                            │
│  usage_events table                                                           │
│      │                                                                        │
│      ▼ (EP-10: wire PricingEngine into collection)                            │
│  PricingEngine.calculate_event_cost()                                         │
│      │                                                                        │
│      ├── resolves ModelPricing ←── model_pricing table                       │
│      │   (effective_from ≤ date ≤ effective_to)                              │
│      │                                                                        │
│      ▼                                                                        │
│  usage_cost_records table (1:1 with usage_events)                             │
│      │                                                                        │
│      ▼ (AggregationService: scheduled/on-demand)                             │
│  daily_cost_summaries table                                                   │
│      │                                                                        │
│      ▼                                                                        │
│  AnalyticsService ──→ /v1/analytics/* endpoints ──→ API Client               │
│                                                                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Database Schema

### model_pricing
```
id              UUID (PK, v7)
provider        VARCHAR(64)
model           VARCHAR(255)
version         VARCHAR(64)
currency        VARCHAR(8)      default='USD'
effective_from  DATE
effective_to    DATE NULL       (NULL = currently active)
prompt_token_price      NUMERIC(20,10)
completion_token_price  NUMERIC(20,10)
cached_token_price      NUMERIC(20,10) NULL
audio_token_price       NUMERIC(20,10) NULL
image_price             NUMERIC(20,10) NULL
embedding_price         NUMERIC(20,10) NULL
is_active       BOOLEAN         default=true
notes           TEXT NULL
[standard BaseModel columns: created_at, updated_at, deleted_at, deleted_by]

UNIQUE: (provider, model, version)
INDEX: (provider, model, effective_from)
INDEX: (provider, model, is_active)
INDEX: (effective_from, effective_to)
```

### usage_cost_records
```
id                    UUID (PK, v7)
usage_event_id        UUID FK usage_events.id CASCADE
organization_id       UUID FK organizations.id CASCADE
project_id            UUID FK projects.id SET NULL
provider_connection_id UUID FK provider_connections.id SET NULL
model_pricing_id      UUID FK model_pricing.id SET NULL
provider              VARCHAR(64)
model                 VARCHAR(255)
currency              VARCHAR(8)
usage_date            DATE
prompt_tokens         INTEGER
completion_tokens     INTEGER
cached_tokens         INTEGER NULL
total_tokens          INTEGER
prompt_cost           NUMERIC(20,8)
completion_cost       NUMERIC(20,8)
cached_cost           NUMERIC(20,8) NULL
total_cost            NUMERIC(20,8)
calculation_version   VARCHAR(32)
[standard BaseModel columns]

UNIQUE: (usage_event_id)    -- 1:1 with usage_events
INDEX: (organization_id, usage_date)
INDEX: (organization_id, provider, usage_date)
INDEX: (organization_id, project_id, usage_date)
INDEX: (organization_id, model, usage_date)
INDEX: (model_pricing_id)
```

### daily_cost_summaries
```
id                      UUID (PK, v7)
organization_id         UUID FK organizations.id CASCADE
project_id              UUID FK projects.id SET NULL   (NULL = org-level)
provider                VARCHAR(64)
model                   VARCHAR(255)
currency                VARCHAR(8)
summary_date            DATE
total_prompt_tokens     BIGINT
total_completion_tokens BIGINT
total_cached_tokens     BIGINT NULL
total_tokens            BIGINT
total_requests          INTEGER
total_cost              NUMERIC(20,8)
total_prompt_cost       NUMERIC(20,8)
total_completion_cost   NUMERIC(20,8)
total_cached_cost       NUMERIC(20,8) NULL
event_count             INTEGER
[standard BaseModel columns]

UNIQUE: (organization_id, project_id, provider, model, currency, summary_date)
INDEX: (organization_id, summary_date)
INDEX: (organization_id, provider, summary_date)
INDEX: (organization_id, project_id, summary_date)
INDEX: (summary_date)
```

---

## 4. Pricing Lifecycle Diagram

```
State 1: New pricing created
┌────────────────────────────────────────────┐
│ version="v1"  effective_from=2024-01-01    │
│               effective_to=NULL (active)   │
└────────────────────────────────────────────┘

State 2: New version added (v1 superseded)
┌────────────────────────────────────────────┐
│ version="v1"  effective_from=2024-01-01    │
│               effective_to=2024-12-31      │ ← closed
└────────────────────────────────────────────┘
┌────────────────────────────────────────────┐
│ version="v2"  effective_from=2025-01-01    │
│               effective_to=NULL (active)   │ ← open
└────────────────────────────────────────────┘

Lookup for 2024-06-15: returns v1
Lookup for 2025-03-01: returns v2
Lookup for 2023-01-01: returns None (PricingNotFoundError)
```

---

## 5. Aggregation Strategy

```
Date: 2026-06-01
Org: org_123

UsageCostRecord rows for (org_123, 2026-06-01):
  row 1: provider=openai, model=gpt-4,    currency=USD, cost=0.05, tokens=1000
  row 2: provider=openai, model=gpt-4,    currency=USD, cost=0.03, tokens=600
  row 3: provider=anthropic, model=claude, currency=USD, cost=0.02, tokens=800

AggregationService.build_daily_summaries(org_123, 2026-06-01) produces:

DailyCostSummary:
  summary 1: openai/gpt-4/USD → total_cost=0.08, total_tokens=1600, event_count=2
  summary 2: anthropic/claude/USD → total_cost=0.02, total_tokens=800, event_count=1
```

---

## 6. Query Patterns

### Analytics queries (AnalyticsService)
- All queries filter `deleted_at IS NULL` and scope by `organization_id`
- Cost queries aggregate on `usage_cost_records` table directly
- Grouped queries (by provider, model, project) use `GROUP BY` with `SUM()`
- Daily trend uses `GROUP BY usage_date ORDER BY usage_date ASC`

### Pricing resolution
- Active pricing: `WHERE effective_to IS NULL AND is_active = TRUE ORDER BY effective_from DESC`
- Historical pricing: `WHERE effective_from <= :date AND (effective_to IS NULL OR effective_to >= :date)`

### Upserts
Both `UsageCostRecordRepository.upsert()` and `DailyCostSummaryRepository.upsert()`
use PostgreSQL `INSERT ... ON CONFLICT DO UPDATE` via `sqlalchemy.dialects.postgresql.insert`.
This is the standard pattern across the codebase (established in EP-08).

---

## 7. Decimal Precision

| Field Type | SQLAlchemy | Python | Precision |
|-----------|-----------|--------|-----------|
| Price per token | `Numeric(20,10)` | `Decimal` | 10dp |
| Computed cost | `Numeric(20,8)` | `Decimal` | 8dp |
| API response | `str` | `str` | Lossless |

All calculations quantize to `Decimal("0.00000001")` with `ROUND_HALF_UP`.

---

## 8. Package Structure

```
app/
├── models/
│   ├── model_pricing.py          # ModelPricing ORM
│   ├── usage_cost_record.py      # UsageCostRecord ORM
│   └── daily_cost_summary.py     # DailyCostSummary ORM
├── repositories/
│   ├── model_pricing_repository.py
│   ├── usage_cost_record_repository.py
│   └── daily_cost_summary_repository.py
├── pricing/
│   ├── __init__.py
│   ├── engine.py                 # PricingEngine
│   └── validator.py              # PricingValidator
├── analytics/
│   ├── __init__.py
│   ├── service.py                # AnalyticsService
│   └── aggregation.py            # AggregationService
├── schemas/
│   ├── pricing.py                # Pricing request/response schemas
│   └── analytics.py              # Analytics response schemas
└── api/v1/
    ├── pricing.py                # /v1/pricing/* endpoints
    └── analytics.py              # /v1/analytics/* endpoints
```
