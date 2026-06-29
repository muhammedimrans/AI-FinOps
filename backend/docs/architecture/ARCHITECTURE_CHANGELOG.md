# Architecture Changelog

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
