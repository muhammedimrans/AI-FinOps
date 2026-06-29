# EP-07 Architecture Review
# OpenAI & Anthropic Provider Integration

**Reviewer role**: Principal Software Architect / Principal Platform Engineer / Principal Security Engineer / Staff Backend Engineer
**Review date**: 2026-06-29
**Branch**: `claude/ai-finops-ep-01-s4d42x`
**Suite**: 668 passing, 0 failing, 30 skipped
**Review scope**: F-033 through F-040; three REST endpoints; no usage collection or streaming

---

## Architecture Score

| Dimension | Score | Rationale |
|-----------|-------|-----------|
| Layering & separation of concerns | 9/10 | Clean HTTP → adapter → API separation; minor factory bypass |
| SOLID compliance | 8/10 | Strong SRP, OCP, DIP; one gap in ABC coverage |
| Testability | 10/10 | Mock injection is hermetic; all 99 tests network-free |
| Security design | 10/10 | No credential leakage path exists by construction |
| Error handling | 8/10 | Good hierarchy; dead exception branches in API layer |
| Scalability readiness | 6/10 | Connection-per-request destroys pool benefits |
| Retry / resilience design | 6/10 | RetryPolicy exists but is never invoked |
| Observability | 7/10 | Latency telemetry present; no structured metrics export |
| Maintainability | 9/10 | Excellent enrichment pattern; low coupling |
| **Overall** | **8/10** | **Solid foundation with two addressable efficiency gaps** |

---

## Executive Summary

EP-07 delivers a well-structured provider integration layer. The security posture is exemplary — credential values have no path to logs, error messages, or telemetry by construction, not by convention. The mock injection pattern enables hermetic testing without any monkey-patching. The error hierarchy is typed and correctly maps HTTP status codes to retryable/non-retryable categories.

Two efficiency gaps require attention before high-traffic production use: (1) each adapter method creates and destroys an `httpx.AsyncClient` (with its connection pool), negating the performance benefit of persistent connections; (2) the `ExponentialRetryPolicy` is fully implemented and tested but is never invoked — the adapter makes exactly one attempt before raising. Neither gap is a correctness issue, but both will surface under load.

**Verdict**: APPROVED WITH MINOR CHANGES

---

## Package Structure Review

```
backend/app/
├── http/                          # F-033 — shared transport layer
│   ├── __init__.py                # clean re-exports
│   ├── auth.py                    # BearerTokenAuth, ApiKeyHeaderAuth, CompositeAuth
│   ├── client.py                  # ProviderHttpClient, map_http_error()
│   ├── retry.py                   # ExponentialRetryPolicy
│   ├── telemetry.py               # RequestTelemetry
│   └── transport.py               # HttpTransport ABC, HttpxTransport
├── providers/
│   ├── adapters/
│   │   ├── anthropic.py           # F-035
│   │   └── openai.py              # F-034
│   ├── credential.py              # F-036 — SecretResolver, CredentialValidator
│   └── info.py                    # F-040 — ProviderInfo
├── schemas/
│   └── providers.py               # TestConnectionResponse, ModelsResponse
└── api/v1/
    └── providers.py               # REST endpoint handlers
```

**Assessment**: Package boundaries are clean and purposeful. `app/http/` is correctly decoupled from `app/providers/` — neither package imports from the other directly; only adapters bridge them. `app/schemas/` holding only API-layer Pydantic models (not provider models) is the correct separation.

---

## Interface Review

### `HttpTransport` ABC (`app/http/transport.py`)

```python
class HttpTransport(ABC):
    async def request(self, method, url, *, headers, params, json, timeout) -> httpx.Response: ...
    async def aclose(self) -> None: ...
    async def __aenter__ / __aexit__
```

**Assessment**: Minimal and correct. The ABC forces exactly the interface `ProviderHttpClient` needs. `aclose()` as separate method (not only via context manager) is correct — allows explicit cleanup paths.

**Gap**: `HttpxTransport.__init__` creates `httpx.AsyncClient` eagerly. When `ProviderHttpClient` is used as `async with self._build_client(key) as client:`, the client is created and destroyed per call. The `httpx.AsyncClient` connection pool is a per-instance resource — it does not persist across calls. This is the primary scalability gap (see Finding ARC-01).

### `ProviderHttpClient` (`app/http/client.py`)

```python
class ProviderHttpClient:
    def __init__(self, *, base_url, auth, provider_type, timeout, mock_transport): ...
    async def get(self, path, *, params, extra_headers, timeout) -> dict[str, Any]: ...
    async def _request(self, method, path, ...) -> dict[str, Any]: ...
    async def aclose(self) -> None: ...
    async def __aenter__ / __aexit__
```

**Assessment**: Strong design. Auth header injection via strategy pattern (`HttpAuth.headers()`) ensures credentials never touch the telemetry path. `X-Request-ID` per request enables correlation without shared state. `map_http_error()` as a standalone function (not method) makes it trivially testable in isolation — this is good design.

**Gap**: `ProviderHttpClient` has no retry loop. It makes one request and raises on failure. `ExponentialRetryPolicy` exists at `app/http/retry.py` but nothing calls it (see Finding ARC-02).

**Gap**: `ProviderHttpClient` exposes only `get()`. The `_request()` method accepts `json` (for POST), but no `post()` convenience method is exposed. This is not a problem for EP-07 (all provider interactions are GET), but EP-08's usage collection will likely need POST. Minor forward-looking note.

### `HttpAuth` strategies (`app/http/auth.py`)

```python
class BearerTokenAuth(HttpAuth): ...         # Authorization: Bearer <key>
class ApiKeyHeaderAuth(HttpAuth): ...        # X-Header-Name: <key>
class CompositeAuth(HttpAuth): ...           # merges multiple strategies
```

**Assessment**: The strategy pattern is correctly applied. `CompositeAuth` allows combining auth schemes (Anthropic needs both `x-api-key` and `anthropic-version`). The `headers()` method returns a new dict each call — no shared mutable state. Correct.

### `SecretResolver` + `CredentialValidator` (`app/providers/credential.py`)

**Assessment**: `SecretResolver.resolve()` is a static method that reads from `os.environ` at call time — the resolved value is never stored on any long-lived object, which is the correct design. The fallback path for unsupported secret stores raises `AuthenticationError` rather than returning an empty string — correct.

`CredentialValidator` validates format before any network call. Key value never appears in any exception message. Correct by inspection.

**Gap**: `SecretResolver` swallows the difference between an unset variable and a variable set to an empty string (`os.environ.get(key, "") == ""`). This is acceptable — both cases produce the same error. If a caller sets `OPENAI_API_KEY=""`, the error message correctly states "not set or empty". No action required.

### `AIProvider` ABC coverage

`get_provider_info()` is implemented on both `OpenAIProvider` and `AnthropicProvider` but is not declared in `AIProvider` ABC (`app/providers/interface.py`). Calling `adapter.get_provider_info()` on a non-EP-07 stub adapter raises `AttributeError`, not `NotImplementedError`. This is a type-safety gap (see Finding ARC-04).

### REST endpoints (`app/api/v1/providers.py`)

**Assessment**: Route handlers are thin — they delegate to adapter methods and translate `ProviderError` subclasses to HTTP status codes. This is correct layering.

**Gap 1** — Dead exception handlers in `test_connection`: `check_connection()` catches all exceptions internally and always returns `ConnectionStatus`. The `except (AuthenticationError, InvalidRequestError)` and `except ProviderError` blocks in `test_connection()` are unreachable. This means the endpoint always returns HTTP 200 even when authentication fails — the failure is reflected in `status.is_connected = False` and `auth_valid = False` in the response body, not in the HTTP status code (see Finding ARC-03).

**Gap 2** — `ProviderFactory`/`ProviderRegistry` bypassed: adapters are instantiated directly via `_get_openai_provider()` / `_get_anthropic_provider()` factory helpers. The EP-06 `ProviderRegistry` singleton is not involved (see Finding ARC-05).

**Gap 3** — `_SUPPORTED_PROVIDERS` disconnected from `ProviderType`: the set `{"openai", "anthropic"}` is maintained manually. Adding a new provider to `ProviderType` does not automatically add it to the endpoint's routing (see Finding ARC-06).

---

## SOLID Compliance

| Principle | Assessment |
|-----------|------------|
| **S** — Single Responsibility | Each class has one job. `ProviderHttpClient` handles HTTP + auth + telemetry but not retry — debatable but acceptable. `RequestTelemetry` is pure logging. `CredentialValidator` is pure format checking. |
| **O** — Open/Closed | New providers follow the documented extension pattern: new adapter file + registration. No existing code requires modification. |
| **L** — Liskov Substitution | Both `OpenAIProvider` and `AnthropicProvider` satisfy `AIProvider`. `ExponentialRetryPolicy` satisfies `RetryPolicy` ABC. `HttpxTransport` satisfies `HttpTransport`. All substitutable. |
| **I** — Interface Segregation | `AIProvider` ABC is appropriately sized — it doesn't force adapters to implement streaming methods. `complete()` and `stream()` raise `NotImplementedError` intentionally. |
| **D** — Dependency Inversion | `ProviderHttpClient` depends on `HttpAuth` (ABC, injected). `HttpxTransport` is injected via constructor. Adapters accept `http_transport` kwargs. Strong inversion at every level. |

---

## Error Handling Review

### Hierarchy correctness

```
ProviderError (base)
├── AuthenticationError       → HTTP 401/403  → not retryable ✓
├── InvalidRequestError       → HTTP 404      → not retryable ✓
├── QuotaExceededError        → not mapped    → not retryable ✓
├── NetworkError              → HTTP 408/504  → retryable ✓
├── RateLimitError            → HTTP 429      → retryable, retry_after_seconds ✓
├── InternalProviderError     → HTTP 500-503  → retryable ✓
└── ProviderConfigurationError → config-time  → not retryable ✓
```

**Assessment**: The mapping in `map_http_error()` is correct. HTTP 408 and 504 both mapping to `NetworkError` (retryable) is correct — both are timeout-class errors. HTTP 429 parsing of `Retry-After` header is robust (handles both `Retry-After` and `retry-after` casing). The catch-all `case _: return ProviderError(...)` for unmapped codes is the right default.

### Exception propagation

`check_connection()` swallows all exceptions and always returns `ConnectionStatus`. This is explicitly documented and correct for a health-check use case — callers always get a structured result. `verify_auth()` and `list_models()` propagate exceptions — correct, as those are imperative operations where failure must be visible to the caller.

---

## Security Architecture Review

### Credential isolation analysis

| Vector | Assessment |
|--------|------------|
| Log lines | No credential can reach logs. `RequestTelemetry` receives only `method`, `url`, `provider` — the auth header dict is never passed. |
| Exception messages | `CredentialValidator` uses generic strings. `SecretResolver` includes the env var *name* (not value) in error text. |
| Stack traces | Credentials are never stored as object attributes after resolution — they live only in local variables within `verify_auth()` / `list_models()`. |
| HTTP request objects | Auth headers are built by `HttpAuth.headers()` and injected into the `headers` dict — this dict is created inside `_request()` and is local to that call. |
| Pydantic `repr` / `__str__` | `Settings.openai_api_key` and `Settings.anthropic_api_key` are `SecretStr` — `repr` shows `'**********'`. |
| Config serialization | `SecretReference` stores only the env var *name* (a string reference), never the value. |

**Conclusion**: The credential isolation is complete. No code path exists where a key value can escape the `_request()` stack frame via any structured output.

### SSRF analysis

Provider adapters construct URLs from `self._config.base_url or _BASE_URL`. The `base_url` field is validated at construction time by `_check_ssrf()` (EP-06.5, `app/providers/config.py`). Cloud-instance metadata hosts, loopback addresses, and private IP ranges are blocked at config validation time. The API layer does not accept a `base_url` from request parameters — adapters are constructed with hard-coded or environment-provided base URLs only. SSRF attack surface is eliminated.

### TLS verification

`HttpxTransport` passes `verify=True` to `httpx.AsyncClient`. This is the default, but it is explicitly set, which prevents accidental downgrade. No path exists to disable TLS verification in the production code path.

---

## Dependency Review

| Dependency | Version | Usage | Risk |
|------------|---------|-------|------|
| `httpx` | 0.28.1 | All provider HTTP calls | Low — stable, well-maintained |
| `pydantic` | v2 | `ProviderInfo`, schemas, config | Low — project-wide |
| `fastapi` | current | REST endpoints | Low — project-wide |
| `python-dotenv` | — | Not used in EP-07 | N/A |

No new dependencies were introduced. EP-07 uses only packages already present in the project's dependency set.

---

## Findings Register

| ID | Severity | Category | Finding | Recommendation |
|----|----------|----------|---------|----------------|
| ARC-01 | HIGH | Scalability | `ProviderHttpClient` builds and destroys `httpx.AsyncClient` (and its connection pool) on every adapter method call. `async with self._build_client(key) as client:` in `verify_auth()` and `list_models()` creates a new client per invocation. Under load this causes OS TCP connection churn, increased latency from repeated TLS handshakes, and potential ephemeral port exhaustion. | Share a single `ProviderHttpClient` instance across calls for the lifetime of the provider adapter instance, or use a module-level connection pool keyed by provider. Addressed in EP-07.5. |
| ARC-02 | HIGH | Reliability | `ExponentialRetryPolicy` is fully implemented at `app/http/retry.py` and has 11 passing unit tests, but `ProviderHttpClient._request()` makes exactly one attempt. Transient `NetworkError` and `InternalProviderError` (retryable errors) are surfaced immediately to the caller with no retry. | Wire `ExponentialRetryPolicy` into `ProviderHttpClient._request()` for retryable error classes. Addressed in EP-07.5. |
| ARC-03 | MEDIUM | API contract | `test_connection` endpoint has unreachable exception handlers. `check_connection()` swallows all exceptions by design. The `except (AuthenticationError, InvalidRequestError)` and `except ProviderError` blocks never execute. The endpoint always returns HTTP 200 — auth failures appear in `auth_valid: false` in the response body, not in the HTTP status code. API consumers must inspect the response body to detect failures. | Document the HTTP-200-always contract on the endpoint. Alternatively, promote the endpoint to raise on `is_connected == False`. Addressed in EP-07.5 with documentation fix only (behavioural change is a breaking contract change). |
| ARC-04 | LOW | Type safety | `get_provider_info()` is not declared in the `AIProvider` ABC. Calling it on a non-EP-07 stub adapter raises `AttributeError`, not `NotImplementedError`. Static type checkers cannot verify the method exists. | Add `@abstractmethod get_provider_info(self, health: HealthStatus | None = None) -> ProviderInfo` to `AIProvider`. Addressed in EP-07.5. |
| ARC-05 | LOW | Consistency | The API layer (`providers.py`) instantiates adapters directly via `_get_openai_provider()` helpers, bypassing `ProviderFactory` and `ProviderRegistry`. Registry lookups, type validation, and `provider_type` cross-checks (EP-06.5 REC-03) are not applied. | Route adapter creation through `ProviderFactory` for consistency. Lower priority — the direct factory helpers are functionally correct for EP-07's two-provider scope. Addressed in EP-08 when the registry will need to support dynamic provider selection. |
| ARC-06 | LOW | Maintainability | `_SUPPORTED_PROVIDERS = {"openai", "anthropic"}` in `providers.py` is a manually maintained set. Adding a new `ProviderType` enum value does not automatically add it to the endpoints. | Derive the supported set from `ProviderType` or the registry. Minor maintenance risk at current scale. Addressed when adding a third provider. |

---

## What Was Done Well

1. **Mock injection pattern**: Accepting `http_transport: httpx.AsyncBaseTransport | None = None` as a constructor keyword argument is the correct approach. It makes all 99 tests hermetic without a single `unittest.mock.patch` call.

2. **`map_http_error()` as a pure function**: Testable in complete isolation from the HTTP client machinery. All 15 test cases in `TestMapHttpError` are simple input/output assertions.

3. **`CompositeAuth` for Anthropic**: Cleanly composes `x-api-key` + `anthropic-version` header injection without conditional logic in the adapter.

4. **Static enrichment pattern**: `list_models()` fetches live IDs then enriches with static metadata. Unknown IDs from the API are included with fallback metadata rather than filtered out. This design is resilient to providers adding new models without a code deploy.

5. **`ProviderInfo` flattening**: Embedding `ProviderCapabilities` fields directly in `ProviderInfo` rather than nesting the frozen dataclass avoids Pydantic v2 schema generation issues with non-Pydantic types. Correct engineering trade-off.

6. **`check_connection()` exception swallowing**: Always returning `ConnectionStatus` regardless of exception type is correct for a health-check operation. The caller always gets a structured, typed result.

7. **`SecretStr` in settings**: Using Pydantic `SecretStr` for `openai_api_key` and `anthropic_api_key` prevents values appearing in `repr` or log serialization of the `Settings` object.

8. **Zero new dependencies**: EP-07 uses only packages already present in the project dependency set.

---

## Architecture Decision Log

| Decision | Rationale | Alternative considered |
|----------|-----------|----------------------|
| Connection-per-request (current) | Simplicity; matches the test injection pattern cleanly | Shared adapter-level pool — requires thread-safety and lifecycle management |
| No retry in `ProviderHttpClient` | Caller responsibility; retry policy is already an ABC | Built-in retry — risks double-retrying when callers also retry |
| `check_connection()` always returns `ConnectionStatus` | Health checks must not raise | Propagate exceptions — breaks the "always get a result" contract |
| `ProviderInfo` fields flattened from `ProviderCapabilities` | Pydantic v2 schema compatibility | Nested dataclass — causes schema generation failure |
| ENV-only secret store in EP-07 | YAGNI — Vault/AWS reserved for EP-09+ | Full secret manager support — significant scope increase |

---

## Architecture Freeze Status

**The EP-07 architecture is frozen** for the following packages and interfaces:

- `app/http/` — `HttpTransport`, `HttpxTransport`, `ProviderHttpClient`, `HttpAuth` strategies, `map_http_error()`, `RequestTelemetry`
- `app/providers/credential.py` — `SecretResolver`, `CredentialValidator`
- `app/providers/info.py` — `ProviderInfo`
- `app/providers/adapters/openai.py` — `OpenAIProvider`, `_CAPABILITIES`, `_MODEL_ENRICHMENT`
- `app/providers/adapters/anthropic.py` — `AnthropicProvider`, `_CAPABILITIES`, `_MODEL_ENRICHMENT`
- REST API contract: `POST /v1/providers/{provider}/test`, `GET /v1/providers/{provider}/models`, `GET /v1/providers/{provider}/info`

**Not frozen** (addressed in EP-07.5 before EP-08 begins):

- Connection lifecycle in `ProviderHttpClient` (ARC-01)
- Retry wiring (ARC-02)
- `AIProvider` ABC coverage of `get_provider_info` (ARC-04)

EP-08 must not begin until ARC-01 and ARC-02 are resolved. ARC-03, ARC-04, ARC-05, ARC-06 are lower priority and may be resolved in EP-07.5 or EP-08.
