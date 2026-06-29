# Architecture Changelog

## [0.9.1] — EP-09 Engineering Review (2026-06-29)

### Review Outcome

**APPROVED WITH MINOR CHANGES** — EP-09 is deployable to development and staging immediately. Two MEDIUM findings (REV-02, REV-05) and five LOW findings must be resolved before or during EP-10. No findings block merging.

### Architecture Score: 8.5 / 10

| Category | Score |
|----------|-------|
| Data Model Design | 9/10 |
| Pricing Engine Architecture | 9/10 |
| Repository Pattern | 9/10 |
| Service Layer Design | 8/10 |
| API Design | 7/10 |
| Financial Accuracy | 9/10 |
| Test Coverage | 9/10 |
| Code Quality | 9/10 |
| **Overall** | **8.5/10** |

### Findings

| ID | Severity | Finding |
|----|----------|---------|
| REV-01 | LOW | Cursor pagination not propagated in filtered `/pricing/models` list path (filtered-path responses always return `next_cursor=null`) |
| REV-02 | MEDIUM | `get_totals_by_org()` sums `total_cost` across all currencies — incorrect in multi-currency deployments; other aggregation methods correctly GROUP BY currency |
| REV-03 | LOW | Soft-delete filter applied manually in aggregation queries (maintainability concern; not a bug) |
| REV-04 | LOW | `POST /pricing/calculate`: `usage_date` defaults to server local date, not UTC — should be documented |
| REV-05 | MEDIUM | `GET /pricing/providers` accepts required `organization_id` query parameter but silently ignores it in SQL — tenant isolation gap |
| REV-06 | LOW | `from datetime import datetime, UTC` inside for loop in `AggregationService.build_daily_summaries` — should be top-level import |
| REV-07 | LOW | `get_top_models()` / `get_top_projects()` fetch all rows from DB and slice in Python — LIMIT should be applied in SQL |

### Review Documents Created

- `docs/knowledge/EP-09-Knowledge-Transfer.md` — full implementation reference (11 sections, 40 engineering concepts), overwrites stub
- `docs/knowledge/EP-09-Architecture-Review.md` — architecture score 8.5/10; findings REV-01 through REV-07; 6 ADRs reviewed
- `docs/knowledge/EP-09-Production-Readiness.md` — production risk register (PRR-01 through PRR-10); 12-item gap analysis

### Security Findings

| ID | Finding |
|----|---------|
| SEC-03 FAIL | No org membership verification — any authenticated user can query any organization's cost data via `organization_id` query parameter |
| SEC-04 FAIL | No RBAC enforcement — `BILLING_READ`, `BILLING_WRITE`, `USAGE_READ` permissions not checked |
| SEC-05 PARTIAL | No row-level security; access control entirely at application layer |

Both SEC-03 and SEC-04 are documented as EP-10 prerequisites throughout the EP-09 codebase.

### EP-09.5 Requirements

No EP-09.5 sprint required. All findings are addressable in EP-10.

Recommended at the start of EP-10:
1. Resolve REV-02: fix multi-currency aggregation in `get_totals_by_org()` before non-USD pricing is configured
2. Resolve REV-05: fix `GET /pricing/providers` to respect `organization_id` or remove the parameter

### EP-10 Prerequisites

1. **Wire PricingEngine into collection pipeline** — `UsageCostRecord` is empty until EP-10 calls `calculate_event_cost()` after each `UsageEvent` is persisted
2. **Org membership verification** — `organization_id` must be verified against authenticated user's JWT claims (SEC-03)
3. **RBAC enforcement** — `BILLING_READ`, `BILLING_WRITE`, `USAGE_READ` permissions (SEC-04)
4. **Derive `organization_id` from JWT claims** — not accepted as an untrusted query parameter
5. **Scheduled aggregation job** — `AggregationService.rebuild_range()` must run nightly to keep `daily_cost_summaries` current
6. **Pricing cascade recalculation** — background job to reprice events when pricing changes

---

## [0.9.0] — EP-09 Cost & Analytics Engine (2026-06-29)

### Changes

EP-09 introduces the Cost & Analytics Engine: versioned pricing, deterministic cost
calculation, cost attribution, analytics queries, and pre-aggregated daily summaries.

### New Tables

| Table | Description |
|-------|-------------|
| `model_pricing` | Versioned pricing per (provider, model) with date ranges |
| `usage_cost_records` | Computed cost record per usage event (1:1 FK) |
| `daily_cost_summaries` | Pre-aggregated daily cost totals for analytics |

### New Packages

| Package | Description |
|---------|-------------|
| `app/pricing/` | `PricingEngine` + `PricingValidator` |
| `app/analytics/` | `AnalyticsService` + `AggregationService` |

### New API Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /v1/pricing/calculate` | Calculate cost for token counts |
| `GET /v1/pricing/models` | List model pricing records |
| `GET /v1/pricing/providers` | List providers with active pricing |
| `POST /v1/pricing/models` | Create pricing record |
| `GET /v1/analytics/usage` | Usage summary |
| `GET /v1/analytics/cost` | Cost summary |
| `GET /v1/analytics/providers` | Per-provider breakdown |
| `GET /v1/analytics/models` | Per-model breakdown |
| `GET /v1/analytics/projects` | Per-project breakdown |
| `GET /v1/analytics/organizations/{id}/summary` | Org summary |

### Key Architecture Decisions

- All monetary values use `decimal.Decimal`; never `float`
- Price-per-token: `Numeric(20,10)`; computed costs: `Numeric(20,8)`
- API serializes Decimal as strings to avoid JSON float precision loss
- `ROUND_HALF_UP` at 8 decimal places for all cost calculations
- Historical pricing resolution via `effective_from`/`effective_to` date ranges
- Upsert pattern (ON CONFLICT DO UPDATE) for cost records and daily summaries
- JWT auth required; org membership verification deferred to EP-10

### Test Results

135 new tests in `tests/test_ep09.py`. Full suite: 910 passed, 30 skipped, 0 failed.

### Migration

`f7a8b9c0d1e2` — creates `model_pricing`, `usage_cost_records`, `daily_cost_summaries`

### Documents Created

- `docs/knowledge/EP-09-Knowledge-Transfer.md`
- `docs/engineering/EP-09-Completion-Report.md`
- `docs/architecture/Cost-Analytics-Architecture.md`

### Stop Condition

**EP-09 is complete. All 135 tests pass. Ready for EP-10.**

---

## [0.8.2] — EP-08 Release Hardening (2026-06-29)

### Changes

All five EP-08 Engineering Review findings resolved. EP-08 is now approved and frozen.

| Finding | Severity | Resolution |
|---------|----------|-----------|
| REV-01 | HIGH | Removed `from unittest.mock import MagicMock` dead import from `app/api/v1/usage.py` |
| REV-02 | HIGH | Added `log.warning("anthropic_usage_api_unavailable", ...)` before `return UsagePage()` in Anthropic adapter |
| REV-03 | MEDIUM | Stub GET endpoints (`/events`, `/runs`, `/checkpoints`, `/providers/{p}/status`) now return HTTP 501 with EP-09 detail message |
| REV-04 | MEDIUM | Migration enum names aligned: `collection_run_status`, `collection_trigger` (with underscores) |
| REV-05 | LOW | `_run_collection_sync()` docstring documents EP-09 deferred persistence |

### Test Results

775 passed, 30 skipped (DB integration), 0 failed. 1 new test added: `TestAnthropicAdapterGetUsage::test_get_usage_logs_warning_on_api_error`.

### Documents Created

- `docs/knowledge/EP-08-Release-Hardening.md` — full sprint report

### Stop Condition

**EP-08 is approved and frozen. The project is ready to begin EP-09 (Cost & Analytics Engine).**

---

## [0.8.1] — EP-08 Engineering Review (2026-06-29)

### Review Outcome

**APPROVED WITH MINOR CHANGES** — EP-08 is deployable to development and staging. Two HIGH findings (REV-01, REV-02) must be resolved before EP-09 begins. Two MEDIUM findings (REV-03, REV-04) may be resolved in the first EP-09 iteration.

### Review Documents

- `docs/knowledge/EP-08-Knowledge-Transfer.md` — full implementation reference (15 sections, 40+ concepts)
- `docs/knowledge/EP-08-Architecture-Review.md` — architecture score 7.5/10; findings REV-01 through REV-05
- `docs/knowledge/EP-08-Production-Readiness.md` — production risk register; 12-item gap analysis

### Findings

| ID | Severity | Finding |
|----|----------|---------|
| REV-01 | HIGH | `from unittest.mock import MagicMock` dead import in production code (`app/api/v1/usage.py`) |
| REV-02 | HIGH | Anthropic `get_usage()` catches all exceptions silently — no log output before returning empty `UsagePage` |
| REV-03 | MEDIUM | GET query endpoints return misleading HTTP 200 with empty data — should return HTTP 501 |
| REV-04 | MEDIUM | Migration enum names (`collectionrunstatus`, `collectiontrigger`) do not match ORM-declared names (`collection_run_status`, `collection_trigger`) |
| REV-05 | LOW | `_run_collection_sync` does not persist to DB — documented EP-08 stop condition; resolved by EP-09 |

### EP-08.5 Required Before EP-09 Production Deployment

1. Resolve REV-01: remove dead `unittest.mock` import from `app/api/v1/usage.py`
2. Resolve REV-02: log exception in Anthropic `get_usage()` before returning empty `UsagePage`
3. Resolve REV-04: align migration enum type names with ORM-declared names
4. Resolve REV-03: return HTTP 501 from stub GET endpoints (or implement in EP-09)

### Security Findings

None new. Multi-tenant isolation and authentication gaps are documented as EP-09 prerequisites (PRR-01, PRR-04 in Production Readiness document).

---

## [0.8.0] — EP-08 Usage Collection Engine (2026-06-29)

### Added

- `app/providers/models.py` — `NormalizedUsageEvent`, `UsagePage` Pydantic models (F-041, F-042)
- `app/providers/interface.py` — `get_usage()` abstract method returning `UsagePage` with cursor/limit pagination (F-042)
- `app/providers/adapters/openai.py` — `get_usage()` via `GET /v1/organization/usage/completions` (F-042)
- `app/providers/adapters/anthropic.py` — `get_usage()` via `GET /v1/usage` with graceful fallback (F-042)
- `app/providers/adapters/` (5 stubs) — `get_usage()` returns empty `UsagePage()` (F-042)
- `app/usage/` — new package: normalizer, validator, service, background (F-042–F-047)
- `app/models/usage_collection_run.py` — `UsageCollectionRun`, `CollectionRunStatus`, `CollectionTrigger` (F-043)
- `app/models/usage_event.py` — `UsageEvent` with `uq_usage_events_dedup` constraint (F-044)
- `app/models/usage_collection_checkpoint.py` — `UsageCollectionCheckpoint` with DEFERRABLE unique constraint (F-045)
- `app/models/provider_usage_summary.py` — `ProviderUsageSummary` (F-045)
- `app/repositories/usage_event_repository.py` — CRUD, upsert, multi-dim filtering (F-043)
- `app/repositories/usage_collection_run_repository.py` — run lifecycle tracking (F-043)
- `app/repositories/usage_collection_checkpoint_repository.py` — incremental state management (F-044)
- `app/repositories/provider_usage_summary_repository.py` — aggregated token summaries (F-045)
- `app/api/v1/usage.py` — 8 REST endpoints at `/v1/usage` (F-049)
- `migrations/versions/20260629_0800_e6f7a8b9c0d1_ep08_usage_collection.py` — Alembic migration
- `tests/test_ep08.py` — 86 unit tests (F-049)

### Design notes

- `UsageEvent.metadata` DB column mapped to `event_metadata` Python attribute (SQLAlchemy `metadata` reservation); upsert uses `UsageEvent.__table__` for table-level INSERT
- Anthropic `get_usage()` silently returns empty page on any error (optional API feature)
- `UsageCollectionService` lazily imports repositories inside `collect()` to avoid circular imports
- Checkpoint constraint is `DEFERRABLE INITIALLY DEFERRED` to support within-transaction upserts
- `get_usage()` interface: old stubs raised `NotImplementedError`; all 7 adapters now satisfy the interface

### Stop condition

EP-08 is complete. Architecture review required before EP-09 (pricing engine).

## [0.7.1] — EP-07 Engineering Review (2026-06-29)

### Review Outcome

**APPROVED WITH MINOR CHANGES** — EP-07 is production-deployable for development and staging. Two efficiency gaps must be resolved in EP-07.5 before high-throughput production traffic or EP-08 begins.

### Review Documents

- `docs/knowledge/EP-07-Knowledge-Transfer.md` — full implementation reference
- `docs/knowledge/EP-07-Architecture-Review.md` — architecture score 8/10; findings ARC-01 through ARC-06
- `docs/knowledge/EP-07-Production-Readiness.md` — production risk register; EP-07.5 gap analysis

### Findings

| ID | Severity | Finding |
|----|----------|---------|
| ARC-01 / PRR-01 | HIGH | Connection pool churn — `httpx.AsyncClient` created/destroyed per adapter method call |
| ARC-02 / PRR-02 | HIGH | `ExponentialRetryPolicy` not wired — `ProviderHttpClient` makes one attempt only |
| ARC-03 / PRR-03 | MEDIUM | `test_connection` endpoint always returns HTTP 200; auth failure is in response body only |
| ARC-04 / PRR-04 | LOW | `get_provider_info()` not declared in `AIProvider` ABC |
| ARC-05 | LOW | `ProviderFactory`/`ProviderRegistry` bypassed in API layer |
| ARC-06 | LOW | `_SUPPORTED_PROVIDERS` set disconnected from `ProviderType` enum |

### EP-07.5 Required Before EP-08

1. Resolve ARC-01: share `ProviderHttpClient` instance across adapter method calls
2. Resolve ARC-02: wire `ExponentialRetryPolicy` into `ProviderHttpClient._request()`
3. Resolve ARC-04: add `get_provider_info()` to `AIProvider` ABC
4. Resolve PRR-05: replace `print()` in `RequestTelemetry` with structured `logging`
5. Resolve ARC-03: document or fix HTTP-200-always contract on `test_connection`

### Security Findings

None. Credential isolation, TLS verification, and SSRF protection are all production-grade.

---

## [0.7.0] — EP-07 OpenAI & Anthropic Provider Integration (2026-06-29)

### Added

- **F-033 Shared HTTP transport** (`app/http/`)
  - `HttpTransport` ABC + `HttpxTransport` — async httpx client; injectable mock transport for unit tests
  - `BearerTokenAuth`, `ApiKeyHeaderAuth`, `CompositeAuth` — auth header strategies
  - `ProviderHttpClient` — wraps transport; adds `X-Request-ID`, `User-Agent`, telemetry; maps HTTP errors
  - `ExponentialRetryPolicy` — implements EP-06 `RetryPolicy` ABC (FIXED, LINEAR, EXPONENTIAL, JITTER)
  - `RequestTelemetry` — structured latency logging; never logs auth headers or key values
- **F-034 OpenAI adapter** (`app/providers/adapters/openai.py`) — full implementation
  - `verify_auth()` — `GET /v1/models` with Bearer token; raises `AuthenticationError` on 401/403
  - `check_connection()` — probes API, caches `_healthy` state, returns `ConnectionStatus`
  - `is_healthy` — returns cached health state (mutable after each `check_connection()`)
  - `list_models()` — live API call; enriches known model IDs with context windows & capability flags
  - `check_capability()` — attribute lookup on `_CAPABILITIES`; no network call
  - `get_provider_info()` — returns `ProviderInfo` with flattened capabilities
- **F-035 Anthropic adapter** (`app/providers/adapters/anthropic.py`) — same interface as F-034
  - Auth: `x-api-key` + `anthropic-version: 2023-06-01` via `CompositeAuth`
  - `anthropic_version` respected from `AnthropicConfig` for future API version pinning
- **F-036 Credential resolution** (`app/providers/credential.py`)
  - `SecretResolver.resolve()` — ENV store only (EP-07); Vault/AWS reserved for EP-09+
  - `CredentialValidator.validate_openai_key()` — prefix (`sk-` / `sk-proj-`) + min-length check
  - `CredentialValidator.validate_anthropic_key()` — prefix (`sk-ant-`) + min-length check
  - Key values never included in error messages or logs
- **F-039 Error mapping** (`map_http_error()` in `app/http/client.py`)
  - 401/403 → `AuthenticationError` (not retryable)
  - 429 → `RateLimitError` with `Retry-After` parsing (retryable)
  - 408/504 → `NetworkError` (retryable)
  - 500/502/503 → `InternalProviderError` (retryable)
  - 404 → `InvalidRequestError` (not retryable)
- **F-040 ProviderInfo model** (`app/providers/info.py`)
  - Pydantic `BaseModel` with flattened `ProviderCapabilities` fields
  - `from_capabilities()` classmethod — convenient construction from adapter constants
- **API endpoints** (`app/api/v1/providers.py`)
  - `POST /v1/providers/{provider}/test` — live auth + connectivity probe
  - `GET  /v1/providers/{provider}/models` — model discovery (live API call)
  - `GET  /v1/providers/{provider}/info` — static metadata + last-known health
- **Settings** — optional `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` fields added as `SecretStr`
- **Tests** — 99 new EP-07 tests in `tests/test_ep07.py`; all hermetic (no network); 668 total suite pass

### Security

- API keys are held only in memory for the duration of a single request; never written to logs, configs, or error messages
- `SecretResolver` reads from env vars only; secret values are never passed to telemetry or logging layers
- `CredentialValidator` checks format before making any network call; key values are never in error messages
- All auth headers built by `HttpAuth` strategies — the credential is never passed to `RequestTelemetry`

### Stop conditions

Completion and streaming (`complete()`, `stream()`) deferred to a later EP.
Usage collection and token counting deferred to EP-08.
Background workers, WebSocket streaming, continuous polling not implemented.

## [0.6.5] — EP-06.5 Provider Framework Hardening (2026-06-29)

### Changed

- **REC-01** `AIProvider` now inherits from `HealthCheckInterface` — eliminates duplicate abstract method signatures; every adapter automatically satisfies both interfaces
- **REC-02** `_check_ssrf()` added to `config.py` — validates `base_url` / `azure_endpoint` at construction; blocks cloud-metadata hosts, loopback, private IPs, and non-HTTP/S schemes; no network calls
- **REC-03** `ProviderConfigurationError` added to `errors.py`; `ProviderFactory.create()` now verifies `instance.provider_type == registry_key` post-construction and raises on mismatch
- **REC-04** `ProviderConfig.provider_type` validated against `ProviderType` enum at construction via `@field_validator`; invalid strings rejected with descriptive error listing valid values
- **REC-05** All 7 adapters now implement `get_usage()`, `check_capability()`, and `is_healthy` (was missing on Ollama and others); `AIProvider.get_usage()` added as abstract method
- **REC-06** `models.py` — full message content hierarchy: `TextContent`, `ImageUrlContent`, `ImageBase64Content`, `AudioContent`, `ToolCall`, `ToolCallContent`, `ToolResultContent`; `MessageContent` discriminated union on `Literal["type"]`; `ProviderRequest.messages` typed as `list[Message]` (backwards-compatible with dict input via Pydantic coercion)
- **REC-07** `SecretStoreType` StrEnum added (`env` / `vault` / `aws_secrets_manager`); `SecretReference.secret_store` typed as `SecretStoreType`; `OllamaConfig` dead validator removed; `_allow_http_base_url: ClassVar[bool]` pattern introduced for SSRF opt-in

### Added

- `ProviderConfigurationError` — exported from `app/providers/__init__.py`
- Message content types — all exported from `app/providers/__init__.py`: `Message`, `MessageRole`, `MessageContent`, `TextContent`, `ImageUrlContent`, `ImageBase64Content`, `AudioContent`, `ToolCall`, `ToolCallContent`, `ToolResultContent`
- `docs/knowledge/EP-06.5-Provider-Hardening.md`
- 56 new unit tests in `tests/test_ep06.py` covering all 7 REC items (total: 188 provider tests, 569 suite-wide)

### Security

- SSRF attack surface for provider `base_url` / `azure_endpoint` eliminated at the config layer; cloud-instance metadata services (169.254.169.254, metadata.google.internal, etc.) always blocked regardless of HTTP/S
- Self-hosted Ollama correctly permitted to use `http://localhost` via `OllamaConfig._allow_http_base_url = True`

## [0.6.0] — EP-06 AI Provider Framework (2026-06-29)

### Added

- `app/providers/` — full provider abstraction layer
  - `AIProvider` ABC (`interface.py`) — F-024
  - `ProviderRegistry` + `get_registry()` singleton (`registry.py`) — F-025
  - `ProviderFactory` (`factory.py`) — F-026
  - `ProviderCapabilities` frozen dataclass (`capabilities.py`) — F-027
  - `ProviderConfig` + 7 typed subclasses (`config.py`) — F-028
  - Provider error hierarchy: `ProviderError`, `RateLimitError`, `AuthenticationError`, `NetworkError`, `QuotaExceededError`, `InvalidRequestError`, `InternalProviderError` (`errors.py`) — F-029
  - `RetryPolicy`, `CircuitBreaker` ABCs + `RetryConfig` + `BackoffStrategy` (`retry.py`) — F-030
  - `HealthCheckInterface` ABC (`health.py`) — F-031
  - Shared Pydantic v2 models: `ModelMetadata`, `ConnectionStatus`, `ProviderRequest`, `ProviderResponse`, `UsageData`, `HealthStatus`, `ModelCapabilityFlag` (`models.py`) — F-032
  - `app/providers/adapters/` — stub adapters for all 7 `ProviderType` values
- `tests/test_ep06.py` — 132 unit tests
- `docs/architecture/Provider-Framework.md`
- `docs/engineering/EP-06-Completion-Report.md`
- `docs/knowledge/EP-06-Knowledge-Transfer.md`

### Design notes

- No real HTTP calls anywhere in EP-06; adapter `complete()` / `verify_auth()` raise `NotImplementedError` pending EP-07
- `ProviderConfig` rejects plaintext credentials in `extra`; all secrets must be `SecretReference`
- `ProviderCapabilities` is a frozen dataclass with `slots=True`; module-level constants avoid per-instance allocation
- Circular import between registry and factory is resolved via lazy import inside `get_registry()`
