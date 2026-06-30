# Architecture Changelog

This document records every architectural change made to AI FinOps since the
original Software Design Document (SDD). It is the authoritative record of
decisions that deviate from, refine, or extend the original design.

Entries are append-only. Never delete or modify a prior entry.

---

## Format

```
## [Version] — [Epic] — [Date]
### Change
### Reason
### Impact
### Related Documents
```

---

## [0.1.0] — EP-01 — 2026-06-29

### Change
Repository foundation established. Python 3.13, FastAPI 0.115+, SQLAlchemy 2.x
async, Pydantic v2, structlog, Alembic, asyncpg.

Project layout:
```
backend/
  app/
    api/        — FastAPI routers and dependency injection
    config/     — Pydantic Settings with SecretStr for credentials
    core/       — AppContainer, logging, redis utilities
    db/         — Base, engine, session, mixins, init_db
    middleware/ — RequestLoggingMiddleware
    models/     — ORM models (empty at EP-01)
    repositories/ — Repository layer (empty at EP-01)
  migrations/   — Alembic migration chain
  tests/        — pytest suite
```

### Reason
SDD §3 and §4 specify the four-layer architecture (API → Service → Repository →
Database). EP-01 establishes the project skeleton and tooling baseline before
any domain models exist.

### Impact
All future Epics build on this foundation. No changes to the layering principle
are permitted without an explicit ADR.

### Related Documents
- SDD §3 (System Architecture)
- SDD §4.1 (Technology Stack)
- EP-01 Knowledge Transfer

---

## [0.2.0] — EP-02 — 2026-06-29

### Change
Database infrastructure implemented:
- `BaseModel` mixin combining `UUIDMixin` (UUIDv7 PKs), `TimestampMixin`
  (`created_at`/`updated_at`), and `SoftDeleteMixin` (`deleted_at`/`deleted_by`)
- `BaseRepository[T]` generic with cursor-based pagination keyed on
  `(created_at, id)`
- `AppContainer` managing engine lifecycle; engine pool tuned for Neon
  serverless (pool_pre_ping, pool_recycle=1800)
- `managed_transaction()` using `begin_nested()` for savepoint-based nested
  transactions in background jobs
- Health (`/health`), readiness (`/ready`), and metrics (`/metrics`) endpoints

### Reason
Establishes the database infrastructure required before any domain tables can
be created. UUIDv7 chosen over SERIAL for time-ordering and distributed
generation without coordination. Cursor pagination chosen over offset to avoid
O(n) scan degradation at scale.

### Impact
- All models must inherit from `BaseModel`
- All PKs are UUID v7
- All queries must filter `deleted_at IS NULL` via `_active_query()`
- Offset pagination is prohibited; all list endpoints use cursor tokens

### Related Documents
- SDD §4.2 (UUIDv7), §4.7 (Index Strategy), §API-7 (Pagination)
- EP-02 Knowledge Transfer
- ADR: UUIDv7 primary keys (to be written)

---

## [0.3.0] — EP-03 — 2026-06-29

### Change
Four core domain models introduced:
- `Organization` (tenant root, OrganizationStatus enum: ACTIVE/SUSPENDED/ARCHIVED)
- `Project` (attribution unit, ProjectEnvironment enum: DEVELOPMENT/STAGING/PRODUCTION)
- `Membership` (email → org RBAC, MembershipRole enum: OWNER/ADMIN/MEMBER/VIEWER)
- `ProviderConnection` (AI provider metadata, ProviderType enum: 7 values; JSONB
  `configuration` for non-sensitive metadata only)

Four repositories: `OrganizationRepository`, `ProjectRepository`,
`MembershipRepository`, `ProviderConnectionRepository`.

One Alembic migration (`a3b4c5d6e7f8`): 4 PostgreSQL enum types, 4 tables, 20 indexes.

Bug fixed: `BaseModel.__init_subclass__` was using `getattr()` (MRO-following)
instead of `cls.__dict__.get()` (own-namespace only), causing all concrete models
to skip auto-index creation silently.

### Reason
Load-bearing entities for multi-tenancy, cost attribution, RBAC, and provider
configuration. Cannot build any subsequent Epic without these four tables.

### Impact
- `Organization.id` is the multi-tenancy root; every future table must carry
  `organization_id` FK (DP-6)
- `Project` is the cost attribution unit; every usage event will FK to a Project
- `Membership.user_email` is a temporary identity anchor (no Users table yet);
  must be migrated to `user_id FK` when Users is introduced in EP-04
- `ProviderConnection.configuration` is non-secret metadata only; secrets are
  stored by reference in the Secrets store (EP-05+)
- All relationships declared with `lazy="select"` at this stage (changed in EP-03.5)

### Related Documents
- SDD §4.4 (Conceptual Data Model), §4.5 (Logical Data Model)
- EP-03 Knowledge Transfer
- EP-03 Architecture Review

---

## [0.3.5] — EP-03.5 — 2026-06-29

### Change: H-001 — Application Startup Wiring
`AppContainer.create()` now calls `init_db()` after engine creation. The
application refuses to start if the database is unreachable (fail-fast). `init_db`
was upgraded from stdlib `logging` to `structlog` for structured JSON output.

### Change: H-002 — Provider Configuration Validation
`validate_provider_configuration()` added to `app/core/validators.py`. Rejects
any `configuration` dict containing credential-pattern keys (`api_key`, `secret`,
`password`, `token`, etc.) with a ValueError that lists all violations. Must be
called by the service layer (EP-04+) before persisting ProviderConnection records.

### Change: H-003 — SQLAlchemy Relationship Loading Policy
All relationships across all four EP-03 models changed from `lazy="select"` to
`lazy="raise"`. Accessing an unloaded relationship now raises
`sqlalchemy.exc.InvalidRequestError` instead of silently emitting synchronous SQL
(which crashes with `MissingGreenlet` in async context).

Relationships with `cascade="all, delete-orphan"` (Organization → Projects,
Memberships, ProviderConnections) also set `passive_deletes=True` to rely on
DB-level ON DELETE CASCADE constraints rather than loading children into Python
for orphan detection.

Service layer (EP-04+) must use `selectinload()` or `joinedload()` whenever
relationships are traversed.

### Change: TD-009 — BaseRepository.update() key validation
`update(**kwargs)` now raises `AttributeError` for unknown attribute names,
preventing silent data loss where unknown keys would be set on the Python instance
but never persisted.

### Change: TD-011 — MembershipRepository.list_by_org_and_role() order param
Added `order: str = "asc"` parameter, making the interface consistent with all
other `list_*` methods.

### Change: TD-012 — OrganizationRepository.slug_exists() efficiency
Replaced full-row ORM fetch with `SELECT EXISTS(SELECT 1 ...)`, avoiding
unnecessary column hydration and reducing I/O cost.

### Change: TD-016 — type: ignore explanations
Added inline comments explaining the three `# type: ignore[attr-defined]`
suppressions in `base_repository.py`, preventing future engineers from removing
them incorrectly.

### Change: TD-018 — Shared test factories
Model factory helpers (`make_org`, `make_project`, `make_membership`,
`make_connection`) moved to `tests/conftest.py` as a single canonical source of
truth. All test files import from conftest rather than defining local copies.

### Change: Integration Test Infrastructure
`tests/integration/` package created with database connectivity tests, migration
verification tests, repository CRUD tests, transaction/rollback tests, and
relationship loading tests. All integration tests are marked with
`@pytest.mark.integration` and skipped automatically when `DATABASE_URL` is not
set.

### Change: Documentation
- `docs/engineering/sqlalchemy-loading-strategy.md` — complete guide to loading
  strategy selection for EP-04+ engineers
- `docs/architecture/ARCHITECTURE_CHANGELOG.md` — this file
- `docs/knowledge/EP-03.5-Foundation-Hardening.md` — completion report

### Reason
The EP-03 Architecture Review identified 5 mandatory prerequisites and 15 minor
technical debt items. EP-03.5 addresses all mandatory prerequisites and 6 of the
minor items before EP-04 begins.

### Impact
- **Breaking change for service layer:** All relationship accesses now require
  explicit eager loading. Any EP-04+ code that accesses `org.projects` without
  `selectinload()` will fail with `InvalidRequestError` at runtime.
- **Validator required:** Service layer MUST call `validate_provider_configuration()`
  before persisting ProviderConnection records.
- **Startup reliability:** Application will not start without a live database
  connection, eliminating a class of silent startup failure.
- No schema changes. No new migrations.

### Related Documents
- EP-03 Architecture Review (Section 14 — Production Readiness Checklist)
- docs/engineering/sqlalchemy-loading-strategy.md
- docs/knowledge/EP-03.5-Foundation-Hardening.md

---

## [0.4.0] — EP-04 — 2026-06-29

### Change: F-013 — User Entity (initial)

`User` ORM model introduced:
- Fields: `id` (UUIDv7), `email` (unique), `display_name`, `is_active` (boolean),
  `avatar_url`, `bio`, plus `created_at`, `updated_at`, `deleted_at`, `deleted_by`
  from `BaseModel`
- External ID prefix: `usr_`
- Repository: `UserRepository` with `get_by_email()`, `email_exists()`, `list_active()`,
  `count_active()`, `create()`, `get_or_raise()`
- Validators: `validate_user_email()`, `validate_display_name()`
- Alembic migration `b1c2d3e4f5a6`: creates `users` table

### Change: F-014 — Membership Refactor

`Membership.user_id` added as nullable FK to `users.id` (ON DELETE CASCADE):
- Expand-Contract pattern: `user_email` preserved; `user_id` nullable for backward compat
- `ix_memberships_user_id` index created
- `User ↔ Membership` bidirectional relationship with `lazy="raise"` on both sides
- Migration included in `b1c2d3e4f5a6`

### Reason
EP-03 established `Membership.user_email` as a temporary identity anchor. EP-04 introduces
the `User` entity and wires the FK from `Membership` to `User`, completing the identity layer
foundation before the authentication service (EP-05) is built.

### Impact
- `User.id` is the identity root; EP-05+ auth tokens will reference `user_id`
- `Membership.user_id` is nullable; service layer must populate both `user_id` and
  `user_email` on all new Membership rows until the contract phase
- All relationships use `lazy="raise"` per H-003 (EP-03.5)

### Related Documents
- SDD §4.4 (User lifecycle), §4.5 (Logical Data Model)
- docs/knowledge/EP-04-Knowledge-Transfer.md

---

## [0.4.1] — EP-04.1 — 2026-06-29

### Change: F-013 Gap Closure — UserStatus Enum

Replaced `is_active: bool` with `status: UserStatus` (ACTIVE / INVITED / DISABLED):
- Aligns with SDD §4.4 lifecycle: `invited → active → disabled`
- PostgreSQL native enum type `user_status` introduced
- `is_active` retained as a Python property (getter + setter) for backward compatibility
- `ix_users_status` index added

### Change: F-013 Gap Closure — Missing Identity Fields

Five new columns added to the `users` table:
- `username` (String 50, nullable, unique via `uq_users_username`)
- `email_verified` (Boolean, NOT NULL, default false)
- `last_login_at` (DateTime TZ, nullable)
- `timezone` (String 64, nullable — IANA identifier)
- `locale` (String 35, nullable — BCP 47 tag)

### Change: F-015 Gap Closure — UserRepository Methods

Four new repository methods:
- `get_by_username(username)` — lookup by unique handle
- `username_exists(username, exclude_id=None)` — SELECT EXISTS uniqueness check
- `search_users(query, limit, cursor)` — ILIKE search across email/username/display_name
- `update_last_login(user_id)` — targeted bulk UPDATE; sets last_login_at and updated_at
- `count_by_status(status)` — count by any UserStatus value

### Change: F-016 Gap Closure — Validators

Three new validators in `app/core/validators.py`:
- `validate_username()` — 3-50 chars, alphanumeric + underscore + hyphen, start/end with alnum
- `validate_locale()` — BCP 47 regex check
- `validate_timezone()` — membership check against `zoneinfo.available_timezones()` (cached)

### Migration: `c3d4e5f6a7b8`

Additive migration over `b1c2d3e4f5a6`. Data migration converts existing `is_active`
values to `status` before dropping the boolean column. Downgrade reverses all steps.

### Reason
Post-merge verification of EP-04 identified 21 gaps across the User entity, repository,
validators, and documentation. EP-04.1 closes all gaps before EP-05 begins.

### Impact
- **Breaking for any EP-04 code that reads `user.status`:** status is now the canonical
  field; `is_active` is a compatibility property only
- **`list_active()` filter changed:** previously `is_active == True`; now `status == ACTIVE`
  (INVITED users are no longer returned from list_active)
- **Service layer action required:** validate username, locale, and timezone before persisting
- No changes to the Membership table or any EP-03 entities

### Related Documents
- docs/knowledge/EP-04-Knowledge-Transfer.md
- EP-04 Verification Report (conversation)

---

## [0.5.0] — EP-05 — 2026-06-29

### Change: Authentication and RBAC Foundation (F-017 through F-022)

#### New models

- **`Session`** (`sessions` table) — refresh-token bearer records; stores SHA-256 hash of
  the raw refresh token, expiry, revocation timestamp, and client metadata (ip, user_agent).
  Prefix: `ses_`.
- **`VerificationToken`** (`verification_tokens` table) — single-use email verification
  tokens; SHA-256 hash + expiry + used_at. Prefix: `vt_`.
- **`PasswordResetToken`** (`password_reset_tokens` table) — single-use password reset
  tokens; SHA-256 hash + expiry + used_at. Prefix: `pr_`.

#### User model extension

`password_hash: String(256) NULL` — Argon2id PHC string. Nullable to support OAuth users.

#### Auth module (`app/auth/`)

- `password.py` — Argon2id hash / verify / needs_rehash
- `tokens.py` — JWT access token (HS256) creation/decoding + opaque refresh token generation + SHA-256 token hashing
- `rbac.py` — `Permission` StrEnum (13 permissions) + `ROLE_PERMISSIONS` mapping + `has_permission()` / `get_permissions()`
- `exceptions.py` — Auth exception hierarchy (`AuthError`, `InvalidCredentialsError`, etc.)
- `service.py` — `AuthService`: login, logout, refresh, verify_email, create_password_reset_token, reset_password

#### FastAPI dependencies (`app/auth/dependencies.py`)

- `CurrentUser` — validates Bearer JWT → User (DB lookup)
- `CurrentOrganization` — resolves `{org_id}` path param → Organization
- `CurrentMembership` — (CurrentUser, CurrentOrganization) → Membership
- `RequirePermission(perm)` — dependency factory enforcing a permission

#### Repositories

- `SessionRepository` — create, revoke, rotate, revoke_all_for_user, list_active_for_user, get_active_by_token_hash
- `VerificationTokenRepository` — create, get_valid_by_hash, mark_used
- `PasswordResetTokenRepository` — create, get_valid_by_hash, mark_used, invalidate_for_user

#### API router (`app/api/v1/auth.py`)

Six endpoints under `/v1/auth/`: login, logout, refresh, verify-email, request-password-reset, reset-password.

#### Migration: `d5e6f7a8b9c0`

Additive migration over `c3d4e5f6a7b8`. Adds `password_hash` to `users` and creates three new tables.

### Reason

EP-05 provides the authentication primitives required before any user-facing resource can be secured. RBAC dependencies are ready to apply to all v1 routes.

### Impact

- **New dependencies in `pyproject.toml`:** `PyJWT>=2.7.0`, `argon2-cffi>=23.1.0`, `email-validator>=2.2.0`
- **New settings:** `jwt_algorithm`, `jwt_access_token_expire_minutes`, `jwt_refresh_token_expire_days` (all have defaults)
- **`JWT_SECRET` must be set in production** — `jwt_secret` validation in production mode deferred to EP-06
- **Email transport deferred:** `create_verification_token()` and `create_password_reset_token()` return the raw token; email provider integration is EP-06
- **F-023 deferred:** rate limiting, account lockout, audit hooks, and access token revocation blocklist are not implemented

### Related Documents

- docs/knowledge/EP-05-Knowledge-Transfer.md
- docs/engineering/EP-05-Completion-Report.md
- docs/security/Authentication-Architecture.md

---

## [0.6.0] — EP-06 — 2026-06-29

### Change

Provider framework established. Introduces the abstract provider layer that
decouples AI API integrations from the rest of the platform.

New modules:

- `app/providers/interface.py` — `AIProvider` ABC with abstract methods:
  `verify_auth()`, `check_connection()`, `list_models()`, `complete()`,
  `get_usage()`, `check_capability()`, `get_provider_info()`
- `app/providers/registry.py` — `ProviderRegistry` maps `provider_type` strings
  to adapter classes; `get_registry()` returns the application singleton
- `app/providers/factory.py` — `ProviderFactory.create(config)` resolves config
  discriminator → adapter class, validates provider_type cross-check, instantiates
- `app/providers/config.py` — Pydantic discriminated union configs:
  `OpenAIConfig`, `AnthropicConfig`, `AzureOpenAIConfig`, `OllamaConfig`,
  `OpenRouterConfig`, `GoogleConfig`, `GrokConfig`; `SecretReference` + `SecretStoreType`
- `app/providers/errors.py` — `ProviderError` hierarchy:
  `AuthenticationError`, `RateLimitError`, `QuotaExceededError`,
  `NetworkError`, `InvalidRequestError`, `InternalProviderError`,
  `ProviderConfigurationError`; `retryable` flag on each subclass
- `app/providers/capabilities.py` — `ProviderCapabilities` dataclass
- `app/providers/models.py` — `ModelMetadata`, `ConnectionStatus`, `HealthStatus`,
  `ModelCapabilityFlag`, `ProviderRequest`, `ProviderResponse`, `UsageData`
- `app/providers/retry.py` — `RetryPolicy` ABC, `RetryConfig`, `BackoffStrategy`
- `app/providers/info.py` — `ProviderInfo` Pydantic model with
  `ProviderInfo.from_capabilities()` factory
- `app/providers/credential.py` — `SecretResolver`, `CredentialValidator`
- Seven adapter stubs in `app/providers/adapters/`:
  `openai.py`, `anthropic.py`, `azure_openai.py`, `google.py`, `grok.py`,
  `ollama.py`, `openrouter.py`

### Reason

The SDD requires a multi-provider AI gateway. EP-06 establishes the abstraction
boundary so every upstream adapter can be implemented, tested, and swapped
independently without touching the API or service layers.

### Impact

- `ProviderType` enum in `app/models/provider_connection.py` is the canonical
  list of all supported providers; adapter registration matches it.
- All adapters are stubs at EP-06; live implementations begin at EP-07.
- `ProviderFactory.create()` enforces that the config's `provider_type` matches
  the registered adapter class — mismatches raise `ProviderConfigurationError`.

### Related Documents

- docs/knowledge/EP-06-Architecture-Review.md

---

## [0.6.5] — EP-06.5 — 2026-06-29

### Change

Provider framework hardening sprint. Closes validation and registration gaps
identified in the EP-06 architecture review.

Key changes:

- `ProviderFactory.create()` now cross-checks `config.provider_type` against the
  registered adapter's `provider_type` property; raises `ProviderConfigurationError`
  on mismatch
- `ProviderRegistry` validates adapter class membership in `ProviderType` enum
  at registration time
- All seven adapter stubs updated so `provider_type` property returns the correct
  `ProviderType` enum member

### Reason

The EP-06 architecture review identified that a misconfigured registry could
silently create an adapter with the wrong provider type. The cross-check makes
this a hard error at factory time.

### Impact

- Any code that calls `ProviderFactory.create()` with a mismatched config will
  receive a `ProviderConfigurationError` instead of a silently wrong adapter.
- No breaking changes to the public `AIProvider` interface.

### Related Documents

- docs/knowledge/EP-06-Architecture-Review.md

---

## [0.7.0] — EP-07 — 2026-06-29

### Change

OpenAI and Anthropic provider integrations implemented. The HTTP transport layer
is fully built out.

New modules:

- `app/http/transport.py` — `HttpxTransport` wraps `httpx.AsyncClient`; accepts
  `mock_transport` for hermetic testing without network calls
- `app/http/auth.py` — `BearerTokenAuth`, `ApiKeyHeaderAuth`, `CompositeAuth`
  strategy objects
- `app/http/client.py` — `ProviderHttpClient` wraps `HttpxTransport`; adds
  auth headers, `X-Request-ID`, `User-Agent`, telemetry, error normalisation
- `app/http/telemetry.py` — `RequestTelemetry` context manager; emits structured
  log entries via `structlog`
- `app/http/retry.py` — `ExponentialRetryPolicy` concrete implementation of
  `RetryPolicy` ABC
- `app/http/error_map.py` — `map_http_error()` maps HTTP status codes to the
  `ProviderError` hierarchy; normalises `Retry-After` header on 429 responses
- `app/providers/adapters/openai.py` — live OpenAI adapter: `verify_auth()`,
  `check_connection()`, `list_models()`, `complete()`, `get_provider_info()`
- `app/providers/adapters/anthropic.py` — live Anthropic adapter: same methods
- `app/api/v1/providers.py` — three REST endpoints:
  `POST /providers/{provider}/test`,
  `GET /providers/{provider}/models`,
  `GET /providers/{provider}/info`
- `app/schemas/providers.py` — `TestConnectionResponse`, `ModelsResponse`

### Reason

EP-07 delivers the first production-ready provider integrations. The HTTP layer
is designed for reuse across all future adapters.

### Impact

- `POST /providers/{provider}/test` returns HTTP 401 on authentication failure
  (not HTTP 200 with `auth_valid=false`).
- Provider enumeration is controlled by `_PRODUCTION_PROVIDERS: frozenset[ProviderType]`
  in `app/api/v1/providers.py`; non-production providers return HTTP 404.
- All tests are hermetic — `httpx.MockTransport` is injected via
  `http_transport` constructor kwarg; no real network calls in CI.

### Related Documents

- docs/knowledge/EP-07-Knowledge-Transfer.md
- docs/knowledge/EP-07-Architecture-Review.md
- docs/knowledge/EP-07-Production-Readiness-Review.md

---

## [0.7.5] — EP-07.5 — 2026-06-29

### Change

EP-07 production hardening sprint (PH-01 through PH-07). Closes all findings
from the combined architecture and production-readiness review before EP-08 begins.

#### PH-01: Shared HTTP Client

`HttpxTransport` is now created once per adapter in `__init__` and stored as
`self._transport`. `ProviderHttpClient` accepts a `transport: HttpxTransport | None`
parameter. When provided, `_owns_transport = False` and `aclose()` is a no-op.
OpenAI and Anthropic adapters expose `async def aclose()`, `__aenter__`, `__aexit__`.

#### PH-02: Retry Integration

`ProviderHttpClient._request()` implements a `while True` retry loop driven by
`RetryPolicy.should_retry(attempt, error)`. `ExponentialRetryPolicy` retries
only `ProviderError` subclasses where `retryable is True` (429, 5xx,
`NetworkError`, `InternalProviderError`). Non-retryable errors (401, 403, 404,
validation) exit immediately. `RateLimitError` honours the `Retry-After` header.
Default: `max_attempts=3`, `initial_delay_seconds=1.0`, `backoff_multiplier=2.0`.

#### PH-03: Factory Usage

`app/api/v1/providers.py` creates all adapters exclusively via
`ProviderFactory(get_registry()).create(config)`. No direct adapter instantiation
remains in any API handler.

#### PH-04: AIProvider Interface Completion

`get_provider_info()` promoted to abstract method in `AIProvider` ABC. All seven
adapter stubs implement it via `ProviderInfo.from_capabilities()`.

#### PH-05: Provider Enumeration

`_PRODUCTION_PROVIDERS: frozenset[ProviderType]` — typed frozenset of enum members.
Non-production `ProviderType` values (e.g. `grok`, `azure_openai`) return HTTP 404.

#### PH-06: HTTP Status Consistency

`POST /providers/{provider}/test` calls `adapter.verify_auth()` directly.
`AuthenticationError` → HTTP 401. `ProviderError` → HTTP 502. No more HTTP 200
with `auth_valid=false`.

#### PH-07: Transport Improvements

`X-Request-ID` UUID header, `User-Agent: ai-finops/<provider_type>`, `post()`
convenience method, correct `aclose()` ownership chain, all logging via `structlog`.

### Reason

Six production risks identified in the EP-07 review. All closed before EP-08
(usage collection) to ensure the HTTP client used by EP-08 is stable.

### Impact

- **Retry delays in tests**: pass `retry_policy=ExponentialRetryPolicy(RetryConfig(max_attempts=1))`
  to disable retries in single-attempt test scenarios.
- **`async with adapter:` pattern** available for OpenAI and Anthropic adapters.
- 688 tests passing, 30 skipped (DB integration).

### Related Documents

- docs/knowledge/EP-07-Release-Hardening.md

---

## [0.11.0] — EP-11 — 2026-06-30

### Change: React SPA Frontend — AI FinOps Enterprise Dashboard

The complete frontend SPA for the AI FinOps platform. A production-grade React 18 application
that visualizes AI API spending across providers, models, projects, and departments.

**Stack:**
- React 18.3 + TypeScript 5.5 (strict: `exactOptionalPropertyTypes`, `noUncheckedIndexedAccess`,
  `noPropertyAccessFromIndexSignature`)
- Vite 5.4 (build) + Vitest 2.1 (tests)
- React Router DOM 6.26 (client-side routing, `BrowserRouter`)
- TanStack Query 5.56 (server state, 5-min staleTime, 3x exponential backoff)
- TanStack Table 8.20 (sortable, filterable, paginated data tables)
- Zustand 5.0 with `persist` middleware (UI state: theme, currency, date range, sidebar)
- Framer Motion 11.11 (page transitions, sidebar collapse, staggered card entry)
- Recharts 2.12 (AreaChart, BarChart, PieChart, ScatterChart)
- Tailwind CSS 3.4 with full design system extension
- React Hook Form 7.53 + Zod 3.23 (settings form validation)
- Lucide React 0.462 (icon set)

**Pages delivered (7):**
1. `/dashboard` — Overview: KPI cards, spend trend AreaChart, provider PieChart, top models
   BarChart, live activity table (60s auto-refresh)
2. `/dashboard/analytics` — Cost Analytics: summary stats, stacked provider AreaChart, TanStack
   Table with sort/filter/search/CSV export/pagination
3. `/dashboard/providers` — Providers: provider card grid with animated cost-share bar,
   comparison BarChart with cost/requests/tokens toggle
4. `/dashboard/models` — Models: medal leaderboard table, efficiency badge by percentile rank,
   ScatterChart performance matrix (cost vs. volume)
5. `/dashboard/projects` — Projects: budget alert banner, project card grid with BudgetBar and
   trend sparklines
6. `/dashboard/organization` — Organization: org-level budget bar, sortable department table
7. `/settings` — Settings: tabbed form (API / Display / Notifications / Data) with Zod validation

**Admin routes (5 placeholder stubs):** `/users`, `/rbac`, `/api-keys`, `/connections`,
`/audit-logs` — show coming-soon UI; backend implementations exist in EP-05 through EP-10.

**Design system:** Dark-first (`#0A0A0F` background, `#4F46E5` Deep Indigo primary).
Glass-morphism cards (`backdrop-filter: blur(12px)`), gradient MetricCard variants, shimmer
loading skeletons, animated sidebar collapse.

**Mock data layer:** `src/lib/mock-data.ts` — seeded RNG (`seed=42`), 90-day daily data,
4 providers, 10 models, 6 projects, 5 departments. Gated by `import.meta.env.DEV` (compile-time
boolean); tree-shaken from production bundles.

**API client:** `src/lib/api.ts` — `VITE_API_BASE_URL` driven, `AbortSignal.timeout(10_000)`,
throws on non-2xx. All monetary values typed as `string` (matching Python Decimal serialization).

**Build output:** `dist/` with `manualChunks` splitting React/router/DOM (vendor), TanStack Query
(query), and app shell (index) into separate browser-cached chunks. Source maps enabled. All seven
feature pages code-split as lazy chunks.

**Known bugs in EP-11 (to be fixed in EP-11.5):**
- BUG-001: `AppLayout.tsx:37` — `key={location.pathname}` uses `window.location` (global) instead
  of `useLocation()` hook — page transition animations never fire
- BUG-002: `Analytics.tsx:119` — Pagination state frozen at `pageIndex: 0`, no
  `onPaginationChange` handler — pagination buttons non-functional
- BUG-003: `Analytics.tsx:44` — Granularity local state not synced to Zustand store — chart
  does not re-fetch when granularity tabs are changed in Analytics page
- BUG-004: `Models.tsx:229` — `r` prop on Recharts `Cell` has no effect in ScatterChart —
  bubble sizing non-functional; requires `<ZAxis>` component

### Reason

The EP-11 design brief specified a React 18 enterprise dashboard as the observation and cost
intelligence layer before live backend integration (EP-12). The frontend is built directly in the
repository (Lovable was out of workspace credits) using the same tooling as the original design
brief.

TypeScript strict mode with the workspace's `noUncheckedIndexedAccess` and
`exactOptionalPropertyTypes` flags required non-trivial accommodations: bracket notation for
`import.meta.env` access, non-null assertions after array index access with null coalescing
fallbacks, and explicit `number | undefined` in optional prop types.

### Impact

- **No backend schema changes.** EP-11 is frontend-only.
- **No new API endpoints.** All data flows through the existing EP-09/EP-10 dashboard endpoints.
- **Mock mode:** `pnpm dev` in `frontend/` runs the full dashboard with seeded mock data.
  No backend required for frontend development.
- **Production mode:** Set `VITE_API_BASE_URL` to the backend URL, run `pnpm build`. Mock code is
  tree-shaken out. SPA routing requires server/CDN to serve `index.html` for all routes.
- **EP-12 prerequisite:** BUG-001 through BUG-004 must be fixed before EP-12 connects live data.
- **EP-13 prerequisite:** All routes currently bypass authentication. EP-13 (Authentication UI)
  must add protected route wrappers before the dashboard is deployed to real users.

### Related Documents

- docs/knowledge/EP-11-Knowledge-Transfer.md
- docs/knowledge/EP-11-Architecture-Review.md
- docs/knowledge/EP-11-UIUX-Review.md
- docs/knowledge/EP-11-Production-Readiness.md

---

---

## [0.11.5] — EP-11.5 — 2026-06-30

### Change

Frontend release hardening sprint. No new features, no backend changes, no API
changes. All 4 confirmed bugs fixed. 3 minor issues cleaned up. Error boundary
infrastructure added. Accessibility baseline established. 27 regression tests
added.

**Bugs fixed:**

| ID | Severity | File | Fix |
|----|----------|------|-----|
| BUG-001 / RH-01 | HIGH | `AppLayout.tsx` | `useLocation()` from react-router-dom replaces global `window.location`; page transition animations now fire correctly |
| BUG-002 / RH-02 | HIGH | `Analytics.tsx` | `onPaginationChange: setPagination` wired to TanStack Table; pagination buttons now functional |
| BUG-003 / RH-03 | MEDIUM | `Analytics.tsx` | Granularity tab click now also calls `useUIStore.getState().setGranularity(g)`; chart re-fetches on tab change |
| BUG-004 / RH-04 | MEDIUM | `Models.tsx` | `ZAxis` added to ScatterChart; bubble size now reflects total spend |

**Minor fixes:**

| ID | File | Fix |
|----|------|-----|
| MINOR-001 | `MetricCard.tsx` | Removed dead `AnimatedNumber` function, unused `useState`/`useEffect`/`useRef` imports, unused `numericValue` variable |
| MINOR-002 | `MetricCard.tsx`, `Projects.tsx` | `Sparkline` and `MiniTrendLine`: guard changed to `if (data.length < 2) return null` — prevents `step = w / 0 = Infinity` NaN coordinates |

**New infrastructure:**

- `src/components/ErrorBoundary.tsx` — React class error boundary with
  `getDerivedStateFromError`, `componentDidCatch` logging, fallback UI, and
  retry reset. Wraps all 12 routes in `App.tsx`.

- `MotionConfig reducedMotion="user"` in `main.tsx` — App-wide Framer Motion
  integration with OS-level `prefers-reduced-motion` preference.

- Keyboard accessibility: sortable `<th>` elements in `Analytics.tsx` and
  `Organization.tsx` now have `tabIndex`, `onKeyDown` (Enter/Space), and
  `aria-sort`.

- Empty states: `Providers.tsx` and `Models.tsx` leaderboard now render
  `EmptyState` / inline message when no data or search returns empty.

**Regression tests:** `src/__tests__/` — 3 files, 27 tests, 0 failures.

**Build verification:**
- `pnpm typecheck`: ✓ 0 errors
- `pnpm test`: ✓ 27/27
- `pnpm build`: ✓ 22 chunks, 8.92s build time

**Pre-existing lint backlog:** 58 ESLint errors (all pre-existing before EP-11.5;
documented in EP-11-Release-Hardening.md). TypeScript compilation passes with 0
errors. Lint backlog deferred to EP-12 sprint setup.

### Reason

The EP-11 production readiness review returned **NOT READY FOR PRODUCTION AS-IS**
with 4 confirmed bugs and a set of hardening items. EP-11.5 resolves all items
required before live backend data can be connected safely in EP-12. The priority
was correctness (all 4 bugs) over polish (no visual redesign).

### Impact

- All 4 confirmed bugs are resolved.
- Page transitions now animate on every SPA navigation.
- Analytics pagination and granularity tabs are fully functional.
- Scatter chart bubble sizes reflect actual spend distribution.
- Any runtime JavaScript error in a page now shows a recovery UI instead of a
  white screen.
- `prefers-reduced-motion` is respected globally.
- Sort tables are keyboard-navigable.
- No backend changes. No API changes. No new routes.

### Related Documents

- docs/knowledge/EP-11-Release-Hardening.md
- docs/knowledge/EP-11-Production-Readiness.md
- docs/knowledge/EP-11-Architecture-Review.md

---

*This changelog is maintained by the engineering team. All architectural changes
must be recorded here before the corresponding Epic is marked complete.*
