# EP-09 Knowledge Transfer: Cost & Analytics Engine

**Epic:** EP-09
**Features:** F-050 through F-057
**Status:** Complete — Engineering Review 2026-06-29
**Date:** 2026-06-29
**Author:** Engineering Review Team

---

## Section 1 — Executive Summary

### What EP-09 Implemented

EP-09 delivers the Cost & Analytics Engine for AI FinOps. It spans features F-050 through F-057 and introduces three new database tables, two new application packages, two new API router files, two new schema files, six new repository classes, and 135 tests.

The core deliverables are:

| Feature | Artifact | Description |
|---------|----------|-------------|
| F-051 | `ModelPricing` | Versioned pricing configuration per (provider, model) |
| F-051 | `UsageCostRecord` | Computed cost for one usage event (1:1 with UsageEvent) |
| F-051 | `PricingEngine` | Deterministic cost calculation using Decimal arithmetic |
| F-051 | `ModelPricingRepository` | Historical pricing lookup with effective date resolution |
| F-051 | `UsageCostRecordRepository` | Idempotent upsert; aggregation queries |
| F-053 | `AnalyticsService` | Read-only analytics: costs by org, provider, model, project |
| F-054 | `DailyCostSummary` | Pre-aggregated daily cost totals per dimension combination |
| F-054 | `DailyCostSummaryRepository` | Summary upsert and date-range queries |
| F-054 | `AggregationService` | Builds and rebuilds daily summaries from cost records |
| F-056 | `PricingValidator` | Field validation and pricing overlap detection |
| F-057 | REST APIs | 10 endpoints across `/v1/pricing` and `/v1/analytics` |

### Business Purpose: Why Cost Visibility Matters for FinOps

AI FinOps exists to answer a deceptively simple question: "How much are we spending on AI, and where?" Without a cost engine, every usage event is a dimensionless token count with no dollar figure attached. Engineers and finance teams cannot:

- Attribute AI spending to the teams, projects, or providers responsible
- Detect cost anomalies before they become budget crises
- Evaluate the cost-efficiency of different models (GPT-4 vs. Claude 3.5 Sonnet vs. Gemini)
- Forecast next month's AI spend with any accuracy
- Build dashboards that allow executive-level visibility into AI ROI

EP-09 transforms raw token counts (collected by EP-08) into monetary costs stored with full attribution dimensions (organization, project, provider, model, date). This is the foundational layer for every downstream FinOps capability.

### Technical Purpose: Pricing Engine vs. Usage Collection

EP-08 (Usage Collection Engine) collects `UsageEvent` records — raw token counts from AI providers. Those records contain no dollar values because pricing is provider-specific, version-specific, and date-dependent. A GPT-4 token costs a different amount in 2024 than in 2025 (providers change prices). A cached prompt token costs less than a fresh prompt token. Embedding tokens are priced differently from completion tokens.

The **Pricing Engine** bridges the gap: given a usage event (provider, model, token counts, date), it resolves the correct pricing record and calculates deterministic costs using exact Decimal arithmetic.

Critically, the Pricing Engine does NOT run inside the collection pipeline in EP-09. The collection pipeline (EP-08) runs on a schedule and must be fast and reliable. Cost calculation is a separate, idempotent operation that can be run after events are collected — and re-run if pricing changes.

### Why Pricing Is Separated from Usage

Usage collection is a provider-facing pipeline. It has its own error modes (rate limits, API unavailability, pagination), its own checkpointing, its own deduplication strategy. Cost calculation is a local, deterministic computation that requires only:
1. The usage event's token counts
2. The pricing record for the correct provider/model/date

Merging them would mean that a missing pricing record causes collection to fail — which would be catastrophic. Instead, usage events with no pricing record can be flagged and repriced when pricing is configured.

### Why Analytics Is Separated from Pricing

The Analytics layer reads cost data that was already computed and persisted. It performs aggregation and serves dashboards. It should never write cost records, recalculate prices, or affect pricing state. The read-only constraint on `AnalyticsService` is explicit and enforced architecturally: the service receives only repository instances, never a PricingEngine.

### Why Cost Attribution Exists as a Distinct Layer

A single `UsageCostRecord` links the original event, the specific pricing version used, and the attribution dimensions (org, project, provider, model). This is the cost attribution layer. Without it, we lose the audit trail: if pricing changes, we cannot know which historical costs were calculated under which pricing version. The `model_pricing_id` FK on `UsageCostRecord` makes historical cost audits possible.

### Why This Architecture Supports Future Providers

Every model is keyed on `(provider, model)` as strings — not enums. Adding a new AI provider (Meta, Mistral, Cohere) requires only inserting pricing records for that provider's models. No schema changes, no code changes in the analytics or pricing layers. The analytics queries already work across all providers generically.

---

## Section 2 — Cost & Analytics Architecture

### Complete Layered Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     AI Provider APIs                            │
│       (OpenAI, Anthropic, Azure, Google, etc.)                  │
└───────────────────────────┬─────────────────────────────────────┘
                            │ GET /usage (EP-08)
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│               Usage Events Layer (EP-08)                        │
│    UsageEvent: provider_request_id, provider, model,           │
│    prompt_tokens, completion_tokens, cached_tokens, timestamp   │
│    Table: usage_events                                          │
└───────────────────────────┬─────────────────────────────────────┘
                            │ PricingEngine.calculate_event_cost()
                            │ (EP-09 — deferred wiring to EP-10)
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│               Pricing Engine (EP-09)                            │
│    PricingEngine:                                               │
│      1. get_pricing_for_event(provider, model, date)            │
│         → ModelPricingRepository.get_for_date()                 │
│      2. calculate_cost(pricing, prompt_tokens, ...)             │
│         → Decimal arithmetic, ROUND_HALF_UP, 8dp               │
│    PricingValidator: overlap detection, field validation        │
│    Table: model_pricing                                         │
└───────────────────────────┬─────────────────────────────────────┘
                            │ upsert via ON CONFLICT DO UPDATE
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│               Cost Attribution Layer (EP-09)                    │
│    UsageCostRecord: one record per UsageEvent (1:1 FK)          │
│    Dimensions: org, project, provider_connection, model,        │
│                currency, usage_date                             │
│    Costs: prompt_cost, completion_cost, cached_cost, total_cost │
│    Audit: model_pricing_id, calculation_version                 │
│    Table: usage_cost_records                                    │
└───────────────────────────┬─────────────────────────────────────┘
                            │ AggregationService.build_daily_summaries()
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│               Aggregation Layer (EP-09)                         │
│    AggregationService: GROUP BY (org, project, provider,        │
│                         model, currency) per day                │
│    DailyCostSummary: pre-aggregated totals for fast queries     │
│    Table: daily_cost_summaries                                  │
└───────────────────────────┬─────────────────────────────────────┘
                            │ read-only queries
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│               Analytics Services (EP-09)                        │
│    AnalyticsService (read-only):                                │
│      get_usage_summary()         → org-level token totals       │
│      get_cost_summary()          → org-level cost totals        │
│      get_provider_breakdown()    → per-provider costs           │
│      get_model_breakdown()       → per-model costs              │
│      get_project_breakdown()     → per-project costs            │
│      get_daily_trend()           → day-by-day cost series       │
│      get_top_models()            → top-N by cost                │
│      get_top_projects()          → top-N by cost                │
└───────────────────────────┬─────────────────────────────────────┘
                            │ REST API
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│               REST API Layer (EP-09)                            │
│    /v1/pricing/*   — pricing management + cost calculation      │
│    /v1/analytics/* — usage and cost analytics                   │
│    Auth: JWT (CurrentUser); RBAC deferred to EP-10              │
└───────────────────────────┬─────────────────────────────────────┘
                            │ future
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│               Future: Dashboard + Alerts (EP-10+)               │
│    Budget alerts, cost forecasting, anomaly detection           │
└─────────────────────────────────────────────────────────────────┘
```

### Layer Responsibilities

| Layer | Responsibility | Write? | Read? |
|-------|----------------|--------|-------|
| Usage Events | Collect raw token counts from providers | EP-08 | Yes |
| Pricing Engine | Resolve pricing version; calculate costs | No | ModelPricing |
| Cost Attribution | Store per-event costs with full dimensions | Yes | No |
| Aggregation | Roll up cost records into daily summaries | Yes | UsageCostRecord |
| Analytics Services | Serve breakdowns and trends | No | Both tables |
| REST API | HTTP interface for all EP-09 operations | Via services | Via services |

### Package Structure

```
backend/
  app/
    models/
      model_pricing.py          # ModelPricing ORM
      usage_cost_record.py      # UsageCostRecord ORM
      daily_cost_summary.py     # DailyCostSummary ORM
    repositories/
      model_pricing_repository.py       # Pricing lookup
      usage_cost_record_repository.py   # Cost upsert + aggregation queries
      daily_cost_summary_repository.py  # Summary upsert + range queries
    pricing/
      __init__.py
      engine.py      # PricingEngine + PricingNotFoundError + CALCULATION_VERSION
      validator.py   # PricingValidator + PricingValidationError
    analytics/
      __init__.py
      service.py     # AnalyticsService (read-only)
      aggregation.py # AggregationService (build daily summaries)
    schemas/
      pricing.py     # ModelPricingCreate, ModelPricingResponse, PriceCalculationRequest/Response
      analytics.py   # UsageSummaryResponse, CostSummaryResponse, breakdown items
    api/
      v1/
        pricing.py   # POST /calculate, GET /models, GET /providers, POST /models
        analytics.py # GET /usage, /cost, /providers, /models, /projects, /organizations/{id}/summary
  migrations/
    versions/
      20260629_0900_f7a8b9c0d1e2_ep09_cost_analytics.py
  tests/
    test_ep09.py     # 135 tests
```

---

## Section 3 — Pricing Domain

### Entity: ModelPricing

Table: `model_pricing` | External ID prefix: `mpr`

`ModelPricing` stores versioned pricing configurations for `(provider, model)` pairs. Multiple versions of pricing can exist for the same pair — one per time period.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | UUID v7 | NOT NULL | Primary key (time-ordered) |
| `created_at` | timestamptz | NOT NULL | Server-side NOW() |
| `updated_at` | timestamptz | NOT NULL | Auto-updated on change |
| `deleted_at` | timestamptz | NULL | NULL = active; non-NULL = soft deleted |
| `deleted_by` | UUID | NULL | Actor who soft-deleted |
| `provider` | VARCHAR(64) | NOT NULL | Provider string: "openai", "anthropic", "azure", etc. |
| `model` | VARCHAR(255) | NOT NULL | Model identifier: "gpt-4", "claude-3-5-sonnet-20241022" |
| `version` | VARCHAR(64) | NOT NULL | Human-readable version tag: "v1", "2024-01-01" |
| `currency` | VARCHAR(8) | NOT NULL | ISO 4217 currency code; default "USD" |
| `effective_from` | DATE | NOT NULL | First date this pricing is valid (inclusive) |
| `effective_to` | DATE | NULL | Last date this pricing is valid (inclusive); NULL = currently active / open-ended |
| `prompt_token_price` | NUMERIC(20,10) | NOT NULL | Price per single prompt token in the configured currency |
| `completion_token_price` | NUMERIC(20,10) | NOT NULL | Price per single completion token |
| `cached_token_price` | NUMERIC(20,10) | NULL | Price per cached token (provider-specific feature) |
| `audio_token_price` | NUMERIC(20,10) | NULL | Price per audio token (provider-specific) |
| `image_price` | NUMERIC(20,10) | NULL | Price per image (provider-specific) |
| `embedding_price` | NUMERIC(20,10) | NULL | Price per 1K tokens for embeddings |
| `is_active` | BOOLEAN | NOT NULL | FALSE = administratively disabled; default TRUE |
| `notes` | TEXT | NULL | Optional human-readable notes about this pricing version |

**Unique constraint:** `uq_model_pricing_provider_model_version` on `(provider, model, version)` — prevents duplicate version tags for the same model.

**Indexes:**
- `ix_model_pricing_provider_model_date` on `(provider, model, effective_from)` — primary lookup index for historical resolution
- `ix_model_pricing_provider_model_active` on `(provider, model, is_active)` — for active pricing queries
- `ix_model_pricing_effective_range` on `(effective_from, effective_to)` — for range overlap checks
- `ix_model_pricing_cursor` on `(created_at, id)` — cursor pagination (auto-created by BaseModel)
- `ix_model_pricing_deleted` on `(deleted_at)` — soft-delete filtering (auto-created by BaseModel)

### Entity: UsageCostRecord

Table: `usage_cost_records` | External ID prefix: `ucr`

`UsageCostRecord` stores the computed cost for a single `UsageEvent`. The unique constraint on `usage_event_id` enforces the 1:1 relationship — exactly one cost record per usage event.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | UUID v7 | NOT NULL | Primary key |
| `created_at` | timestamptz | NOT NULL | Record creation time |
| `updated_at` | timestamptz | NOT NULL | Last update time |
| `deleted_at` | timestamptz | NULL | Soft delete timestamp |
| `deleted_by` | UUID | NULL | Soft delete actor |
| `usage_event_id` | UUID | NOT NULL | FK → `usage_events.id` ON DELETE CASCADE |
| `organization_id` | UUID | NOT NULL | FK → `organizations.id` ON DELETE CASCADE |
| `project_id` | UUID | NULL | FK → `projects.id` ON DELETE SET NULL; NULL = no project attribution |
| `provider_connection_id` | UUID | NULL | FK → `provider_connections.id` ON DELETE SET NULL |
| `model_pricing_id` | UUID | NULL | FK → `model_pricing.id` ON DELETE SET NULL; audit trail of which pricing was used |
| `provider` | VARCHAR(64) | NOT NULL | Denormalized from UsageEvent for query efficiency |
| `model` | VARCHAR(255) | NOT NULL | Denormalized from UsageEvent |
| `currency` | VARCHAR(8) | NOT NULL | From the resolved ModelPricing record |
| `usage_date` | DATE | NOT NULL | Date portion of event timestamp — used for aggregation |
| `prompt_tokens` | INTEGER | NOT NULL | Input token count (default 0) |
| `completion_tokens` | INTEGER | NOT NULL | Output token count (default 0) |
| `cached_tokens` | INTEGER | NULL | Cached token count if reported |
| `total_tokens` | INTEGER | NOT NULL | Sum of all token types |
| `prompt_cost` | NUMERIC(20,8) | NOT NULL | Computed: prompt_tokens × prompt_token_price, rounded 8dp |
| `completion_cost` | NUMERIC(20,8) | NOT NULL | Computed: completion_tokens × completion_token_price |
| `cached_cost` | NUMERIC(20,8) | NULL | Computed: cached_tokens × cached_token_price (if both present) |
| `total_cost` | NUMERIC(20,8) | NOT NULL | prompt_cost + completion_cost + (cached_cost or 0) |
| `calculation_version` | VARCHAR(32) | NOT NULL | Algorithm version string, currently "1.0" |

**Unique constraint:** `uq_usage_cost_records_event` on `(usage_event_id)` — enforces 1:1 with UsageEvent.

**Indexes:**
- `ix_usage_cost_records_org_date` on `(organization_id, usage_date)` — primary analytics index
- `ix_usage_cost_records_org_provider_date` on `(organization_id, provider, usage_date)` — provider breakdown
- `ix_usage_cost_records_org_project_date` on `(organization_id, project_id, usage_date)` — project breakdown
- `ix_usage_cost_records_org_model_date` on `(organization_id, model, usage_date)` — model breakdown
- `ix_usage_cost_records_pricing_id` on `(model_pricing_id)` — repricing queries

### Entity: DailyCostSummary

Table: `daily_cost_summaries` | External ID prefix: `dcs`

`DailyCostSummary` stores pre-aggregated daily cost totals grouped by `(organization_id, project_id, provider, model, currency)`. This avoids full `usage_cost_records` scans for common dashboard queries. Built and maintained by `AggregationService`.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | UUID v7 | NOT NULL | Primary key |
| `created_at` | timestamptz | NOT NULL | |
| `updated_at` | timestamptz | NOT NULL | |
| `deleted_at` | timestamptz | NULL | |
| `deleted_by` | UUID | NULL | |
| `organization_id` | UUID | NOT NULL | FK → `organizations.id` ON DELETE CASCADE |
| `project_id` | UUID | NULL | FK → `projects.id` ON DELETE SET NULL; NULL = org-level summary (all projects) |
| `provider` | VARCHAR(64) | NOT NULL | |
| `model` | VARCHAR(255) | NOT NULL | |
| `currency` | VARCHAR(8) | NOT NULL | |
| `summary_date` | DATE | NOT NULL | The date being summarized |
| `total_prompt_tokens` | BIGINT | NOT NULL | Sum of all prompt tokens on this date |
| `total_completion_tokens` | BIGINT | NOT NULL | Sum of all completion tokens |
| `total_cached_tokens` | BIGINT | NULL | Sum of cached tokens (NULL if none reported) |
| `total_tokens` | BIGINT | NOT NULL | Sum of all token types |
| `total_requests` | INTEGER | NOT NULL | Count of requests (equals event_count) |
| `total_cost` | NUMERIC(20,8) | NOT NULL | Sum of total_cost across all cost records |
| `total_prompt_cost` | NUMERIC(20,8) | NOT NULL | Sum of prompt_cost |
| `total_completion_cost` | NUMERIC(20,8) | NOT NULL | Sum of completion_cost |
| `total_cached_cost` | NUMERIC(20,8) | NULL | Sum of cached_cost (NULL if none) |
| `event_count` | INTEGER | NOT NULL | Number of UsageCostRecords aggregated |

**Unique constraint:** `uq_daily_cost_summaries` on `(organization_id, project_id, provider, model, currency, summary_date)` — one summary row per dimension combination per day.

Note: `project_id` IS NULL in the unique constraint is treated as a distinct value in PostgreSQL, meaning org-level summaries (NULL project) coexist correctly with project-level summaries.

### Relationships Between Models

```
organizations
    │ (1)
    ├──→ (N) UsageCostRecord.organization_id
    └──→ (N) DailyCostSummary.organization_id

UsageEvent (EP-08)
    │ (1)
    └──→ (0..1) UsageCostRecord.usage_event_id  [UNIQUE — 1:1]

ModelPricing
    │ (1)
    └──→ (N) UsageCostRecord.model_pricing_id   [SET NULL on delete — audit trail preserved]

projects
    │ (1)
    ├──→ (N) UsageCostRecord.project_id         [SET NULL on delete]
    └──→ (N) DailyCostSummary.project_id        [SET NULL on delete]

provider_connections
    │ (1)
    └──→ (N) UsageCostRecord.provider_connection_id [SET NULL on delete]
```

### Effective Dates and Versioning

Pricing versioning uses a date-range pattern:

```
provider=openai, model=gpt-4:
  version="v1": effective_from=2024-01-01, effective_to=2024-12-31
  version="v2": effective_from=2025-01-01, effective_to=NULL  ← currently active
```

The `effective_to=NULL` convention means "open-ended" or "currently active." The `PricingValidator` enforces that no two active pricing records for the same `(provider, model)` have overlapping date ranges. This invariant ensures that the historical lookup always returns exactly one record (or zero if no pricing covers that date).

### Historical Pricing Lookup Pattern

The lookup pattern is implemented in `ModelPricingRepository.get_for_date()`:

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

The `ORDER BY effective_from DESC LIMIT 1` ensures the most recently effective version is returned if overlap validation was not perfectly enforced historically.

### Decimal Precision

Two precision levels are used:

| Type | Column Type | Scale | Use Case |
|------|------------|-------|----------|
| Price per token | `NUMERIC(20, 10)` | 10 decimal places | Prices like 0.0000000150 are representable |
| Computed cost | `NUMERIC(20, 8)` | 8 decimal places | Final cost values for storage and analytics |

The 20-digit total precision allows prices for high-token-count events without overflow. For context, 1 billion tokens at $0.000001/token = $1,000, which requires only 8 significant digits — well within the 20-digit ceiling.

### Currency Handling

Currency is stored as an ISO 4217 string (e.g., "USD", "EUR") on both `ModelPricing` and `UsageCostRecord`. The currency is propagated from the pricing record at calculation time. All analytics queries group by currency when aggregating — this prevents mixing USD and EUR totals, which would produce incorrect sums. The current system defaults to "USD" but the schema is multi-currency ready.

### Future Extensibility

The schema supports:
- **Multi-currency:** currency is stored on every record; analytics already group by currency
- **Regional pricing:** add a `region` column to `ModelPricing` and extend the lookup query
- **Per-tier pricing:** add a `tier` column (e.g., "enterprise", "standard")
- **New token types:** add nullable columns like `audio_token_price` (already present) for new modalities
- **New providers:** no schema changes — just insert pricing records for the new provider

---

## Section 4 — Pricing Engine

### Architecture Overview

The `PricingEngine` (`app/pricing/engine.py`) is the single source of truth for cost computation. It is a pure-function service: given a pricing record and token counts, it returns a deterministic cost dictionary. It holds no state beyond the repository reference.

### Historical Pricing Lookup: get_for_date()

`PricingEngine.get_pricing_for_event(provider, model, usage_date)` delegates to `ModelPricingRepository.get_for_date()`. This method finds the pricing record whose effective date range covers the usage date:

```python
# Pseudocode
WHERE effective_from <= usage_date
  AND (effective_to IS NULL OR effective_to >= usage_date)
  AND is_active = TRUE
  AND deleted_at IS NULL
ORDER BY effective_from DESC
LIMIT 1
```

If no record is found, `PricingNotFoundError` is raised. The API layer maps this to HTTP 404.

### Version Resolution

The lookup is inclusive on both ends:
- `effective_from <= usage_date` — the version is active on or before the usage date
- `effective_to >= usage_date` — the version has not yet expired by the usage date
- `effective_to IS NULL` — the version is still active (open-ended)

The `ORDER BY effective_from DESC LIMIT 1` ensures that if multiple records match (which should not happen after overlap validation), the most recently effective one wins.

### Decimal Calculations with ROUND_HALF_UP

All arithmetic in `calculate_cost()` uses Python's `decimal.Decimal` type. The quantization constant is:

```python
_QUANT = Decimal("0.00000001")  # 8 decimal places
```

Every cost is quantized individually before summing:

```python
prompt_cost = (Decimal(prompt_tokens) * pricing.prompt_token_price).quantize(
    _QUANT, rounding=ROUND_HALF_UP
)
completion_cost = (Decimal(completion_tokens) * pricing.completion_token_price).quantize(
    _QUANT, rounding=ROUND_HALF_UP
)
cached_cost = (Decimal(cached_tokens) * pricing.cached_token_price).quantize(
    _QUANT, rounding=ROUND_HALF_UP
) if (cached_tokens is not None and pricing.cached_token_price is not None) else None

total_cost = (
    prompt_cost + completion_cost + (cached_cost or Decimal(0))
).quantize(_QUANT, rounding=ROUND_HALF_UP)
```

`ROUND_HALF_UP` is the financial rounding convention (0.5 rounds away from zero). Python's default `ROUND_HALF_EVEN` (banker's rounding) is preferred for statistical work but non-intuitive for billing customers. The choice ensures costs match customer expectations.

### CALCULATION_VERSION Constant

```python
CALCULATION_VERSION = "1.0"
```

This constant is stored on every `UsageCostRecord`. Its purpose is to allow future recalculation workflows to identify records computed under an old algorithm version. If the calculation formula changes in a future EP (e.g., adding a volume discount multiplier), the version would be bumped to "2.0" and records with version "1.0" could be selectively repriced.

### PricingNotFoundError and Graceful Fallback

`PricingNotFoundError` is raised when no pricing record covers the requested provider/model/date combination. This is an expected, non-exceptional case (pricing may not be configured for a new model). The API layer converts it to HTTP 404. The collection pipeline (once wired in EP-10) should handle it by skipping cost calculation for that event and flagging the event for repricing once pricing is configured.

The exception includes the provider, model, and date in the message to make debugging straightforward.

### Separation from Usage Collection

The pricing calculation must NOT run inside the usage collection pipeline for these reasons:
1. **Missing pricing would abort collection:** If a model has no pricing configured, cost calculation would fail, preventing the event from being persisted.
2. **Pricing changes require retroactive recalculation:** If pricing is corrected, all historical events must be repriced. This is simpler if repricing is a separate operation.
3. **Different failure modes:** Network failures during collection should not cause cost calculation errors, and vice versa.
4. **Performance isolation:** Cost calculation can be batched, rate-limited, and retried independently of collection.

### Cost Formula

```
prompt_cost       = prompt_tokens × prompt_token_price
completion_cost   = completion_tokens × completion_token_price
cached_cost       = cached_tokens × cached_token_price  (if both non-None)
total_cost        = prompt_cost + completion_cost + (cached_cost or 0)

All values rounded to ROUND_HALF_UP at 8 decimal places.
```

---

## Section 5 — Cost Attribution

### How Costs Are Attributed

Every `UsageCostRecord` carries six attribution dimensions:

| Dimension | Column | Purpose |
|-----------|--------|---------|
| Organization | `organization_id` | Multi-tenant isolation; billing unit |
| Project | `project_id` | Team-level attribution; nullable (unattributed events) |
| Provider | `provider` | Which AI provider was used |
| Provider Connection | `provider_connection_id` | Which API key/connection was used |
| Model | `model` | Which specific model was used |
| Usage Date | `usage_date` | When the usage occurred (DATE, not timestamp) |

The `usage_date` is the DATE portion of the usage event's timestamp — deliberately truncated to a day. This enables efficient GROUP BY aggregation without timestamp arithmetic.

### 1:1 Relationship Between UsageEvent and UsageCostRecord

```
UsageEvent (1) ──[uq_usage_cost_records_event]──→ (0..1) UsageCostRecord
```

This 1:1 relationship is enforced by the unique constraint on `usage_event_id`. There can be at most one cost record per event. An event with no cost record means pricing was not available at collection time. The upsert pattern allows repricing: when pricing is added or corrected, the same event is re-costed and the `ON CONFLICT DO UPDATE` replaces all cost fields.

### Aggregation Flow

```
UsageCostRecord (per-event detail)
    │
    │ AggregationService.build_daily_summaries(org_id, date)
    │
    │ GROUP BY (organization_id, project_id, provider, model, currency)
    │ WHERE usage_date = target_date
    │
    ▼
DailyCostSummary (pre-aggregated daily totals)
    │
    │ AnalyticsService reads both tables:
    │   - UsageCostRecord for detailed breakdowns (no need to hit summary table)
    │   - DailyCostSummary available for calendar-based queries
    ▼
REST API
```

### Attribution Dimensions ASCII Diagram

```
                    ┌──────────────────────────┐
                    │     UsageCostRecord       │
                    ├──────────────────────────┤
         ┌──────────┤ organization_id           │
         │          ├──────────────────────────┤
         │ ┌────────┤ project_id (nullable)     │
         │ │        ├──────────────────────────┤
         │ │ ┌──────┤ provider                  │
         │ │ │      ├──────────────────────────┤
         │ │ │ ┌────┤ model                     │
         │ │ │ │    ├──────────────────────────┤
         │ │ │ │ ┌──┤ usage_date                │
         │ │ │ │ │  └──────────────────────────┘
         │ │ │ │ │
         ▼ ▼ ▼ ▼ ▼
   DailyCostSummary grouped by all five dimensions
   ↓
   AnalyticsService breaks down by any single dimension
     - By org: SUM(total_cost) WHERE org_id = X AND date BETWEEN A AND B
     - By provider: GROUP BY provider
     - By model: GROUP BY provider, model
     - By project: GROUP BY project_id
     - By day: GROUP BY usage_date
```

---

## Section 6 — Analytics Layer

### AnalyticsService Read-Only Methods

`AnalyticsService` (`app/analytics/service.py`) is a pure read-only service. It accepts `UsageCostRecordRepository` and `DailyCostSummaryRepository` via constructor injection and exposes these methods:

| Method | Repository Used | Description |
|--------|----------------|-------------|
| `get_usage_summary(org, start, end)` | UsageCostRecord | Total tokens and request count for org in date range |
| `get_cost_summary(org, start, end)` | UsageCostRecord | Total cost for org in date range |
| `get_provider_breakdown(org, start, end)` | UsageCostRecord | Per-provider cost breakdown |
| `get_model_breakdown(org, start, end)` | UsageCostRecord | Per-model cost breakdown |
| `get_project_breakdown(org, start, end)` | UsageCostRecord | Per-project cost breakdown |
| `get_daily_trend(org, start, end)` | UsageCostRecord | Day-by-day cost totals |
| `get_top_models(org, start, end, limit)` | UsageCostRecord | Top-N models by cost |
| `get_top_projects(org, start, end, limit)` | UsageCostRecord | Top-N projects by cost |

All methods return `dict` or `list[dict]`. The API layer converts these to typed Pydantic response models with Decimal-as-string serialization.

### AggregationService

`AggregationService` (`app/analytics/aggregation.py`) is a write service:

- `build_daily_summaries(org_id, target_date)` — runs one SQL GROUP BY query, then upserts one `DailyCostSummary` per result row
- `rebuild_range(org_id, start_date, end_date)` — iterates day by day calling `build_daily_summaries` for each; returns total count

### Why Analytics Is Read-Only

The `AnalyticsService` is structurally prevented from writing:
1. It has no database session — only repository instances
2. The repositories it receives are query-only repositories (UsageCostRecordRepository, DailyCostSummaryRepository)
3. No `upsert`, `create`, or `soft_delete` methods are called from `AnalyticsService`

This separation prevents accidental modification of financial records during a read path.

### Separation of Read Path from Write Path

```
Write path:
  PricingEngine → UsageCostRecordRepository.upsert()
  AggregationService → DailyCostSummaryRepository.upsert()

Read path:
  AnalyticsService → UsageCostRecordRepository (aggregation queries)
  AnalyticsService → DailyCostSummaryRepository (range queries)
  REST API → AnalyticsService
```

These paths share repository classes but not instances — each request gets a fresh session and fresh repository instances from `app/api/deps.py`.

---

## Section 7 — Repository Layer

### ModelPricingRepository

Located at `app/repositories/model_pricing_repository.py`. Methods:

| Method | Query Pattern | Description |
|--------|--------------|-------------|
| `get_active_for_model(provider, model)` | `effective_to IS NULL AND is_active = TRUE ORDER BY effective_from DESC LIMIT 1` | Returns the currently active pricing (open-ended) |
| `get_for_date(provider, model, date)` | `effective_from <= date AND (effective_to IS NULL OR effective_to >= date)` | Historical pricing lookup — the core EP-09 operation |
| `list_for_provider(provider)` | All active records for provider, ordered by model, effective_from DESC | Used for admin listing |
| `list_for_model(provider, model)` | All pricing versions for a pair, newest first | Used by PricingValidator overlap check |
| `get_by_version(provider, model, version)` | Unique lookup by (provider, model, version) | Used to check for duplicate version before insert |

**Index strategy:** The primary lookup (`get_for_date`) benefits from `ix_model_pricing_provider_model_date` on `(provider, model, effective_from)`. PostgreSQL can satisfy the `effective_from <= date` predicate from this index. The `effective_to` check uses `ix_model_pricing_effective_range` on `(effective_from, effective_to)`.

### UsageCostRecordRepository

Located at `app/repositories/usage_cost_record_repository.py`. Methods:

| Method | Description |
|--------|-------------|
| `get_by_event(usage_event_id)` | Lookup by FK — used after upsert to return the persisted record |
| `upsert(record)` | PostgreSQL `INSERT ... ON CONFLICT (uq_usage_cost_records_event) DO UPDATE` |
| `get_totals_by_org(org, start, end)` | Aggregate: total_cost, total_tokens, count |
| `get_totals_by_provider(org, start, end)` | Aggregate: GROUP BY provider, currency |
| `get_totals_by_model(org, start, end)` | Aggregate: GROUP BY provider, model, currency |
| `get_totals_by_project(org, start, end)` | Aggregate: GROUP BY project_id, currency |
| `get_daily_trend(org, start, end)` | Aggregate: GROUP BY usage_date, currency, ORDER BY date ASC |

**Upsert pattern:** The upsert uses `pg_insert().on_conflict_do_update()` with `constraint="uq_usage_cost_records_event"`. This is the correct PostgreSQL idiom for idempotent upserts. After the upsert statement executes, a second SELECT is issued to return the persisted record (PostgreSQL's `INSERT ... RETURNING` is not used here because the conflict clause updates, not inserts, and the ORM model may need to be refreshed).

**Aggregation queries:** All aggregation uses `func.coalesce(..., 0)` and `func.coalesce(..., Decimal(0))` to handle empty result sets gracefully. The `deleted_at.is_(None)` filter is applied explicitly in all aggregation queries (not inherited from `_active_query()`).

### DailyCostSummaryRepository

Located at `app/repositories/daily_cost_summary_repository.py`. Methods:

| Method | Description |
|--------|-------------|
| `upsert(summary)` | `ON CONFLICT (uq_daily_cost_summaries) DO UPDATE` — replaces all aggregated values |
| `get_for_date_range(org, start, end)` | All summaries for org in range, ordered by date |
| `get_by_provider(org, start, end)` | Summaries ordered by date then provider |
| `get_by_model(org, start, end)` | Summaries ordered by date then model |

**upsert return value:** After the upsert, the repository issues a SELECT to return the persisted summary. The SELECT uses `project_id IS NULL` vs `project_id = :id` conditioning based on whether the summary's project_id is None, correctly handling the PostgreSQL NULL-in-unique-constraint behavior.

### BaseRepository Inheritance

All three EP-09 repositories inherit from `BaseRepository[T]` which provides:
- `_active_query()` — base SELECT filtering `deleted_at IS NULL`
- `create(instance)` — adds to session + flush + refresh
- `get(id)`, `get_or_raise(id)` — active record lookup
- `soft_delete(instance, deleted_by)` — sets deleted_at
- `list_page(limit, cursor, order)` — cursor-based pagination on `(created_at, id)`
- `count(extra_filters)` — active record count

### ON CONFLICT DO UPDATE Pattern

Both upsert implementations follow the same pattern:

```python
stmt = pg_insert(Model.__table__).values(**values)
stmt = stmt.on_conflict_do_update(
    constraint="constraint_name",
    set_={
        "field1": stmt.excluded.field1,
        "updated_at": func.now(),
    },
)
await self._session.execute(stmt)
await self._session.flush()
```

The `stmt.excluded` reference refers to the proposed-to-be-inserted row, which is the standard PostgreSQL idiom. After the upsert, a SELECT is issued to return the final state of the record.

### Performance Notes

- Analytics queries hit `usage_cost_records` directly (not via `daily_cost_summaries`). This is correct for EP-09 where the summary table may not be fully populated. When the summary table is fully maintained (EP-10 scheduled jobs), analytics queries can optionally be redirected to it.
- The analytics aggregation queries use multi-column composite indexes: `ix_usage_cost_records_org_date` `(organization_id, usage_date)` is the primary filter for all analytics queries.
- `COALESCE` in aggregation queries prevents NULL from propagating into sums — important because `SUM()` of an all-NULL column returns NULL, not 0.

---

## Section 8 — REST APIs

### Pricing Endpoints

Router: `app/api/v1/pricing.py` | Prefix: `/v1/pricing`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/v1/pricing/calculate` | JWT required | Calculate cost for given token counts |
| GET | `/v1/pricing/models` | JWT required | List model pricing records (filterable) |
| GET | `/v1/pricing/providers` | JWT required | List providers with active pricing |
| POST | `/v1/pricing/models` | JWT required | Create new pricing record (admin) |

**POST /v1/pricing/calculate**
- Request: `PriceCalculationRequest` — provider, model, prompt_tokens, completion_tokens, cached_tokens, usage_date (optional, defaults to today)
- Response: `PriceCalculationResponse` — all cost fields as strings, pricing_date, calculation_version
- Error: HTTP 404 if no pricing found for provider/model/date
- Auth: `CurrentUser` (JWT validated); org membership not enforced until EP-10

**GET /v1/pricing/models**
- Query params: `organization_id` (required), `provider` (optional), `model` (optional), `is_active` (optional), `limit` (1-100, default 20)
- Response: `ModelPricingListResponse` — items list, total, has_more, next_cursor
- Logic: If `provider` and `model` both provided → `list_for_model()`; if only `provider` → `list_for_provider()`; otherwise → `list_page()`
- Note: `next_cursor` is always `None` — cursor pagination not fully wired for filtered queries

**GET /v1/pricing/providers**
- Query params: `organization_id` (required)
- Response: `list[str]` — distinct provider names with active (non-deleted, is_active=True) pricing
- Note: `organization_id` is required as a query param but not used to filter providers — this is the EP-10 gap

**POST /v1/pricing/models**
- Request: `ModelPricingCreate` — all pricing fields; effective_to validated > effective_from in schema
- Response: `ModelPricingResponse` (HTTP 201)
- Validation flow: 1) field validation via `PricingValidator.validate_new_pricing()`, 2) overlap check via `validate_no_overlap()`, 3) duplicate version check via `get_by_version()`
- Errors: HTTP 422 for field validation failure, HTTP 409 for overlap or duplicate version

### Analytics Endpoints

Router: `app/api/v1/analytics.py` | Prefix: `/v1/analytics`

| Method | Path | Auth | Response Type | Description |
|--------|------|------|---------------|-------------|
| GET | `/v1/analytics/usage` | JWT | `UsageSummaryResponse` | Total token counts for org in date range |
| GET | `/v1/analytics/cost` | JWT | `CostSummaryResponse` | Total costs for org in date range |
| GET | `/v1/analytics/providers` | JWT | `list[ProviderBreakdownItem]` | Per-provider cost breakdown |
| GET | `/v1/analytics/models` | JWT | `list[ModelBreakdownItem]` | Per-model cost breakdown (optional provider filter) |
| GET | `/v1/analytics/projects` | JWT | `list[ProjectBreakdownItem]` | Per-project cost breakdown |
| GET | `/v1/analytics/organizations/{org_id}/summary` | JWT | `OrgSummaryResponse` | Combined usage + cost summary |

All analytics endpoints accept `organization_id` (as query param or path param), `start_date`, `end_date` as query parameters.

### Pagination and Filtering

EP-09 analytics endpoints do not implement cursor pagination — they return all results for the given date range. The `GET /pricing/models` endpoint uses `list_page()` from `BaseRepository` for cursor pagination but does not propagate the cursor in the filtered-path responses.

### Decimal Serialization as Strings

All Decimal monetary values in API responses are serialized as strings:
- `ModelPricingResponse.from_orm_model()` explicitly calls `str()` on each Decimal field
- Analytics schema classes declare cost fields as `str` type (e.g., `total_cost: str`)
- The API layer converts `Decimal` to `str` with `str(result["total_cost"])` before constructing response objects

This prevents JSON float precision loss. Clients should parse these string fields as `Decimal` or equivalent precision types, not `float`.

### Authentication and Org Membership Deferral to EP-10

All endpoints use `CurrentUser` (from `app.auth.dependencies`) to enforce JWT authentication. This means:
- Unauthenticated requests return HTTP 401
- The authenticated user's `organization_id` membership is NOT verified
- `organization_id` is accepted as a query parameter and trusted without validation

This is explicitly documented in comments throughout both API files as "NOTE: org membership verification is deferred to EP-10." EP-10 must add:
1. Org membership check: `verify_user_is_member(user, organization_id)`
2. RBAC enforcement: `RequirePermission(Permission.BILLING_READ)` / `BILLING_WRITE` / `USAGE_READ`
3. JWT org binding: derive `organization_id` from JWT claims instead of query parameter

---

## Section 9 — Validation Layer

### PricingValidator

`PricingValidator` (`app/pricing/validator.py`) provides two validation methods:

**`validate_new_pricing(pricing: ModelPricing) -> None`**

Checks the following in order, collecting all errors before raising:

| Check | Error Message |
|-------|--------------|
| `provider` is non-empty string | "provider must be non-empty" |
| `model` is non-empty string | "model must be non-empty" |
| `version` is non-empty string | "version must be non-empty" |
| `currency` is non-empty string | "currency must be non-empty" |
| `effective_from` is not None | "effective_from must not be None" |
| `effective_to > effective_from` (if both set) | "effective_to must be after effective_from" |
| `prompt_token_price >= 0` | "prompt_token_price must be >= 0" |
| `completion_token_price >= 0` | "completion_token_price must be >= 0" |
| `cached_token_price >= 0` (if not None) | "cached_token_price must be >= 0 if provided" |
| `audio_token_price >= 0` (if not None) | "audio_token_price must be >= 0 if provided" |
| `image_price >= 0` (if not None) | "image_price must be >= 0 if provided" |
| `embedding_price >= 0` (if not None) | "embedding_price must be >= 0 if provided" |

All errors are collected and raised together in a single `PricingValidationError` with semicolon-separated messages. This allows the API to return all validation issues in one response.

**`validate_no_overlap(repo, pricing) -> None`**

Fetches all existing pricing versions for `(provider, model)` and checks for date range conflicts with the new pricing record.

Two date ranges `[A_from, A_to]` and `[B_from, B_to]` overlap if:
```
A_from <= B_to  (where NULL to = +infinity)
AND B_from <= A_to  (where NULL to = +infinity)
```

The method skips the record's own ID (for update operations). If any overlap is found, `PricingValidationError` is raised with a message identifying the conflicting existing version.

### Pricing Overlap Detection Logic

With NULL treated as open-ended (+infinity):

```python
new_from_lte_ex_to = ex_to is None or new_from <= ex_to   # new starts before existing ends
ex_from_lte_new_to = new_to is None or ex_from <= new_to   # existing starts before new ends
if new_from_lte_ex_to and ex_from_lte_new_to:
    raise PricingValidationError(...)
```

**Adjacent ranges do NOT overlap:** If existing `effective_to = 2024-12-31` and new `effective_from = 2025-01-01`, then:
- `new_from_lte_ex_to`: `2025-01-01 <= 2024-12-31` → FALSE

So adjacent ranges are correctly allowed.

### Invalid Currency Handling

The validator only checks that `currency` is non-empty. It does NOT validate against an ISO 4217 allowlist. This means "XYZ" would pass validation. Future work should add a currency enum or allowlist validation. For now, this is acceptable because pricing records are admin-only writes.

### Negative Pricing Prevention

All price fields are validated `>= 0`. The check also handles `None` for required fields (`prompt_token_price` and `completion_token_price`) — if either is None, the validation fails with the appropriate error message.

### Invalid Effective Dates

The validator checks:
1. `effective_from` must not be None
2. If `effective_to` is provided: `effective_to > effective_from` (strictly greater)
3. Equal dates (`effective_to == effective_from`) are rejected — a pricing version must be valid for at least one full day

---

## Section 10 — Testing Strategy

### Test Count and Location

- **EP-09 test file:** `tests/test_ep09.py`
- **EP-09 tests:** 135 tests
- **Full suite:** 910 passed, 30 skipped (DB integration tests), 0 failed
- All EP-09 tests are hermetic — no live database, no network calls

### Test Coverage by Class

| Class | Tests | Key Scenarios |
|-------|-------|---------------|
| `TestModelPricing` | 12 | field types, Decimal, optional fields, effective dates, repr |
| `TestUsageCostRecord` | 8 | field types, Decimal, FK fields, calculation_version |
| `TestDailyCostSummary` | 11 | field types, BigInteger tokens, nullable project, event_count |
| `TestModelPricingRepository` | 7 | get_active, get_for_date, list_for_provider, list_for_model, get_by_version |
| `TestUsageCostRecordRepository` | 7 | get_by_event, upsert, all 5 aggregation query methods |
| `TestDailyCostSummaryRepository` | 5 | upsert, fallback, date range, by_provider, by_model |
| `TestPricingEngine` | 13 | basic cost, Decimal type enforcement, cached tokens, zero tokens, precision 8dp, ROUND_HALF_UP, PricingNotFoundError |
| `TestPricingValidator` | 20 | all field validations, zero prices OK, overlap, adjacent ranges OK, self-ID skipped |
| `TestAnalyticsService` | 11 | all 8 methods, top-N limit, date strings, org ID string |
| `TestAggregationService` | 4 | no records, rebuild range, single day, rows → summaries |
| `TestPricingAPI` | 9 | 401 guards (4), mock auth: list models, list providers, calculate 404, calculate 200 |
| `TestAnalyticsAPI` | 13 | 401 guards (6), mock auth: all 6 endpoints |
| `TestPricingSchemas` | 6 | from_orm_model, Decimal-as-string, PriceCalculationResponse, create validation, invalid dates |
| `TestAnalyticsSchemas` | 8 | all response types, project_id=None case |

### Decimal Precision Tests

`test_calculate_cost_precision_8dp` verifies the exponent of the returned Decimal:
```python
assert result["prompt_cost"].as_tuple().exponent == -8
```

This directly verifies that quantization produced exactly 8 decimal places, not merely that the value is numerically close.

### Historical Pricing Tests

The repository tests mock the session and verify that `get_for_date()` and `get_active_for_model()` correctly handle found and not-found cases. The validator overlap tests verify the boundary condition: adjacent ranges `(2024-01-01 to 2024-12-31)` and `(2025-01-01 to NULL)` do not overlap.

### Why the Strategy Is Production-Grade

1. **Hermetic:** No live database — all tests use `AsyncMock` for the database session
2. **Type-aware:** Tests verify `isinstance(result["prompt_cost"], Decimal)` — not just numeric equality
3. **Error-path coverage:** Every validation error branch is independently tested
4. **API auth guards:** Every endpoint is tested for 401 without a bearer token
5. **Contract tests:** Schema tests verify Decimal-as-string serialization
6. **Boundary tests:** Zero tokens, None prices, adjacent date ranges all covered

---

## Section 11 — Top 40 Engineering Concepts

1. **EP-09 implements F-050 through F-057** — the Cost & Analytics Engine, transforming raw token counts from EP-08 into monetary costs and analytics.

2. **Three new database tables** — `model_pricing`, `usage_cost_records`, `daily_cost_summaries`, each with the standard `BaseModel` pattern (UUID v7 PK, timestamps, soft delete).

3. **ModelPricing stores versioned pricing per (provider, model) pair** — multiple versions can exist, differentiated by `effective_from`/`effective_to` date ranges.

4. **`effective_to = NULL` means "currently active"** — an open-ended pricing record that has not yet been superseded. Only one open-ended record per provider/model should exist at any time.

5. **Price-per-token columns use NUMERIC(20, 10)** — 10 decimal places are needed to represent sub-cent per-token prices (e.g., $0.000000015 per token).

6. **Computed cost columns use NUMERIC(20, 8)** — 8 decimal places for final cost values that are sums of price × token count.

7. **Never use float for monetary values** — Python `float` is IEEE 754 binary floating point and introduces precision errors in financial calculations. All monetary arithmetic uses `decimal.Decimal`.

8. **`ROUND_HALF_UP` at 8 decimal places** — the financial rounding convention, implemented by `quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)`.

9. **`CALCULATION_VERSION = "1.0"`** — stored on every UsageCostRecord to enable future repricing workflows that need to identify records computed under an old algorithm.

10. **`PricingNotFoundError`** — raised (not swallowed) when no pricing record covers the requested provider/model/date. Surfaces as HTTP 404 in the API.

11. **Historical pricing lookup** — `ModelPricingRepository.get_for_date()` uses `effective_from <= date AND (effective_to IS NULL OR effective_to >= date)` to find the correct historical version.

12. **The `get_for_date()` index** — `ix_model_pricing_provider_model_date` on `(provider, model, effective_from)` is the primary support index for the historical lookup query.

13. **1:1 between UsageEvent and UsageCostRecord** — enforced by `uq_usage_cost_records_event UNIQUE(usage_event_id)`. There is at most one cost record per usage event.

14. **Upsert supports repricing** — `UsageCostRecordRepository.upsert()` uses `ON CONFLICT (uq_usage_cost_records_event) DO UPDATE` so that recalculating costs for the same event overwrites the old values without creating duplicates.

15. **`model_pricing_id` as audit trail** — `UsageCostRecord.model_pricing_id` records exactly which pricing version was used. If pricing is later corrected, the records computed under the old version are identifiable.

16. **`usage_date` is a DATE, not a timestamp** — truncated to day granularity for efficient GROUP BY in aggregation queries. Time-of-day is irrelevant for cost rollup purposes.

17. **Denormalization of provider and model on UsageCostRecord** — eliminates the need to join back to `usage_events` for every analytics query. The join cost is paid once at record creation time.

18. **`DailyCostSummary` unique constraint** — `uq_daily_cost_summaries` on `(organization_id, project_id, provider, model, currency, summary_date)` ensures one summary row per dimension combination per day.

19. **`project_id = NULL` in DailyCostSummary** — means the summary covers all projects (org-level rollup). PostgreSQL treats NULL as distinct in unique constraints, so org-level and project-level summaries coexist.

20. **`AggregationService.build_daily_summaries()`** — runs a SQL GROUP BY aggregation over `usage_cost_records` for one org + one date, then upserts into `daily_cost_summaries`.

21. **`AggregationService.rebuild_range()`** — iterates day by day calling `build_daily_summaries` for each. Suitable for backfilling, repricing, or nightly batch refresh.

22. **`AnalyticsService` is read-only** — it has no session, no write repository methods. Only reads `UsageCostRecord` via aggregation queries and optionally reads `DailyCostSummary`.

23. **Analytics queries currently use `UsageCostRecord` not `DailyCostSummary`** — because the summary table may not be populated in EP-09. In EP-10, when scheduled aggregation is wired, summaries can be used for calendar queries.

24. **Decimal serialization as strings in API responses** — prevents JSON float precision loss. `ModelPricingResponse.from_orm_model()` calls `str()` on each Decimal field. Analytics schema classes declare cost fields as `str`.

25. **`PricingValidator.validate_new_pricing()`** — collects all validation errors into a list before raising, so the API can return all issues at once.

26. **Pricing overlap detection** — two date ranges overlap if `A_from <= B_to AND B_from <= A_to` (with NULL treated as +infinity). Adjacent ranges (where one ends the day before the other begins) do NOT overlap.

27. **`validate_no_overlap()` skips the same record ID** — supports update operations where the record being updated is in the `list_for_model()` results.

28. **`POST /v1/pricing/models` validation order** — 1) field validation, 2) overlap check, 3) duplicate version check. Order matters: field validation must pass before the overlap check can safely use the `effective_from` field.

29. **HTTP 409 for overlap and duplicate version** — distinguishes "the request is syntactically valid but conflicts with existing data" from HTTP 422 "the request is syntactically invalid."

30. **JWT required on all EP-09 endpoints** — `CurrentUser` dependency from `app.auth.dependencies` is present on every handler. Unauthenticated requests return 401.

31. **Org membership NOT verified in EP-09** — `organization_id` is accepted as a query parameter and trusted without checking that the authenticated user is a member of that organization. This is the primary security gap deferred to EP-10.

32. **`GET /pricing/providers`** — returns distinct provider strings from `model_pricing` where `is_active=TRUE` and `deleted_at IS NULL`. Useful for populating UI dropdowns.

33. **`GET /analytics/models?provider=X`** — the provider filter is applied in Python (after the DB query returns all models), not in SQL. This is acceptable for EP-09 where the model count is small.

34. **`GET /analytics/organizations/{org_id}/summary`** — makes two DB calls (one for usage summary, one for cost summary) and merges them in the API layer. This is the combined view that a dashboard would use.

35. **BaseRepository cursor pagination** — `list_page()` encodes `(created_at, id)` as a base64 JSON cursor. The `GET /pricing/models` endpoint uses this for the unfiltered list path, but `next_cursor` is not propagated in filtered-path responses (a minor gap).

36. **`BigInteger` for aggregated token counts in DailyCostSummary** — `BIGINT` (64-bit) prevents overflow when summing millions of token counts per day. Individual event token counts use `INTEGER` (32-bit, max ~2 billion tokens per event, which is sufficient).

37. **Alembic migration `f7a8b9c0d1e2`** — creates all three tables with correct precision types, constraints, FK constraints, and 17 indexes. Revises `e6f7a8b9c0d1` (EP-08 migration). Downgrade reverses all changes in strict reverse order (child tables before parent).

38. **`app/models/__init__.py` import order** — EP-09 models are imported after EP-08 models because `UsageCostRecord` has an FK to `usage_events`. Import order must match FK dependency order for SQLAlchemy mapper initialization.

39. **`PricingEngine` is stateless** — it holds only a reference to the repository. Multiple concurrent requests can safely share a `PricingEngine` instance (though in the current implementation, one is instantiated per request in the API handler).

40. **EP-10 prerequisites** — the major items deferred: (1) wire `PricingEngine` into the usage collection pipeline to populate `UsageCostRecord`; (2) enforce org membership on analytics/pricing endpoints; (3) add RBAC permissions `BILLING_READ`, `BILLING_WRITE`, `USAGE_READ`; (4) scheduled aggregation jobs; (5) pricing cascade recalculation on pricing changes; (6) derive `organization_id` from JWT claims.
