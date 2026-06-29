# EP-07 Knowledge Transfer
## OpenAI & Anthropic Provider Integration

**Date**: 2026-06-29
**Branch**: `claude/ai-finops-ep-01-s4d42x`
**Commit**: `5bddde2`
**Suite**: 668 passing / 0 failing / 30 skipped (live DB)

---

## 1. Implementation Summary

### Business Purpose

EP-07 answers the question: *"Is this AI provider reachable, authenticated, and what models does it offer?"*

Before AI FinOps can track costs and usage (EP-08), it must prove connectivity to each provider. Users configure a provider connection, provide an API key, and EP-07 validates that the key works, the provider is reachable, and reports the available models. This is the prerequisite gate before any cost data flows.

### Architecture Purpose

EP-07 establishes the **shared HTTP infrastructure** (`app/http/`) that every future provider adapter will use. Rather than each adapter implementing its own HTTP logic, all adapters share:
- A single async HTTP client abstraction
- A single authentication strategy hierarchy
- A single error normalisation layer
- A single telemetry context manager

This is an investment: the transport written in EP-07 serves EP-08 (usage collection), EP-09 (completion), and all subsequent provider EPs without modification.

### Security Purpose

EP-07 establishes the credential security contract used by all future EPs:
1. API keys are never stored — only a *reference* (env var name) is stored
2. Keys are resolved at request time, held in memory for the duration of one call
3. Keys never appear in log lines, error messages, stack traces, or HTTP responses
4. Format validation happens before any network call — failed keys fail fast without leaking the value

### Future Roadmap

```
EP-07  ←  YOU ARE HERE
  Provider connectivity, auth validation, model discovery

EP-08  ←  NEXT
  Usage collection: scheduled pulls from OpenAI /usage, Anthropic /usage
  Writes raw usage records to ClickHouse
  Uses EP-07's HTTP transport, auth, and error handling unchanged

EP-09  ←  FUTURE
  Completion: calling provider APIs to generate text
  Adds POST /v1/messages (Anthropic), POST /v1/chat/completions (OpenAI)
  Builds on EP-07's ProviderHttpClient

EP-10  ←  FUTURE
  Vault / AWS Secrets Manager secret stores
  SecretResolver already has the extension point reserved
```

---

## 2. HTTP Transport Layer

### Why a Shared Transport Exists

Without a shared transport, each adapter would:
- Implement its own httpx client configuration
- Duplicate timeout logic
- Implement its own error mapping
- Have no consistent request ID strategy
- Be untestable without monkey-patching

With a shared transport, every adapter gets connection pooling, structured telemetry, typed errors, and test-injectable mocks at zero incremental cost.

### Architecture Diagram

```
┌────────────────────────────────────────────────────────────┐
│                   Provider Adapter                          │
│  (OpenAIProvider / AnthropicProvider)                      │
│                                                            │
│  async with self._build_client(key) as client:            │
│      data = await client.get("/v1/models")                │
└──────────────────────┬─────────────────────────────────────┘
                       │
                       ▼
┌────────────────────────────────────────────────────────────┐
│                 ProviderHttpClient                          │
│                                                            │
│  • Calls auth.headers() to get auth headers               │
│  • Generates X-Request-ID (UUID4)                         │
│  • Sets User-Agent: aifinops/0.1.0                        │
│  • Calls RequestTelemetry context manager                 │
│  • Delegates actual network call to HttpxTransport        │
│  • Maps httpx exceptions → NetworkError                   │
│  • Maps HTTP status codes → ProviderError subclasses      │
│  • Parses JSON response body                              │
└──────────────────────┬─────────────────────────────────────┘
                       │
                       ▼
┌────────────────────────────────────────────────────────────┐
│                  HttpxTransport                            │
│                                                            │
│  • Wraps httpx.AsyncClient                                │
│  • Provides connection pooling (one pool per client)      │
│  • Accepts mock_transport for test injection             │
│  • verify=True enforces TLS certificate validation        │
└────────────────────────────────────────────────────────────┘
                       │
                       ▼
              Real network / MockTransport
```

### Transport (`app/http/transport.py`)

`HttpTransport` is an ABC defining one method:

```python
async def request(method, url, *, headers, params, json, timeout) -> httpx.Response
```

`HttpxTransport` implements it by wrapping `httpx.AsyncClient`. The `mock_transport` parameter accepts any `httpx.AsyncBaseTransport`, enabling `httpx.MockTransport` injection in tests without any monkey-patching.

**Connection pooling**: `httpx.AsyncClient` maintains a per-instance connection pool. In the current design, `ProviderHttpClient` (and thus `HttpxTransport`) is created per-method-call and immediately closed after use. This means the pool is rebuilt on each call. See the Architecture Review for the implications.

### Authentication (`app/http/auth.py`)

Authentication uses the **Strategy pattern**:

```
HttpAuth (ABC)
├── BearerTokenAuth          → Authorization: Bearer <token>
│                               Used by: OpenAI
├── ApiKeyHeaderAuth         → <header_name>: <key>
│                               Used by: Anthropic (x-api-key)
│                               Used by: Anthropic (anthropic-version)
└── CompositeAuth            → Merges multiple strategies (last-write wins)
                                Used by: Anthropic (key + version together)
```

Auth headers are built by calling `auth.headers()`, which returns a fresh dict each call. The credential string never leaves the `HttpAuth` subclass — it flows into the headers dict and goes directly to the HTTP layer without touching telemetry.

### Telemetry (`app/http/telemetry.py`)

`RequestTelemetry` is a synchronous context manager (used inside async code):

```python
with RequestTelemetry(method="GET", url=url, provider="openai") as tel:
    response = await transport.request(...)
    tel.status_code = response.status_code
```

On exit it logs either `provider_http_done` (success) or `provider_http_error` (exception), with latency in milliseconds and a request UUID. **No auth headers, no key values, no response body are logged.**

The design reserves hook points for OpenTelemetry span creation (marked with `# Future:` comments), making it trivially easy to add distributed tracing later.

### Retry Policy (`app/http/retry.py`)

`ExponentialRetryPolicy` implements the `RetryPolicy` ABC from EP-06 (F-030). It supports four backoff strategies:

| Strategy | Formula |
|----------|---------|
| FIXED | `delay = initial` |
| LINEAR | `delay = initial × attempt` |
| EXPONENTIAL | `delay = initial × multiplier^(attempt-1)` |
| JITTER | `base × (0.5 + random × 0.5)` |

All strategies respect `max_delay_seconds`. The policy only retries errors where `error.retryable is True` (i.e., `RateLimitError`, `NetworkError`, `InternalProviderError`).

**Important**: In EP-07, the retry policy is available as a tool but is not wired into `ProviderHttpClient`. Retry logic is the caller's responsibility. EP-08's usage collection service should use `ExponentialRetryPolicy` when scheduling collection runs.

### Request IDs

Every request gets a `uuid.uuid4()` string injected as `X-Request-ID`. This ID appears in:
- The request header sent to the provider (for provider-side correlation)
- The `provider_http_start` and `provider_http_done`/`provider_http_error` log events

It does NOT appear in error messages sent back to API callers.

### Timeouts

Timeout is configured at the `ProviderConfig` level (`timeout_seconds`, default 30.0) and passed through to `HttpxTransport.request()`. `httpx.TimeoutException` is caught by `ProviderHttpClient` and re-raised as `NetworkError`.

---

## 3. Provider Framework Integration

### How Everything Fits Together

```
User Request
     │
     ▼
ProviderConfig ──────────────────────────► SecretReference
(OpenAIConfig /                            (secret_store=ENV,
 AnthropicConfig)                           secret_key="OPENAI_API_KEY")
     │                                             │
     ▼                                             ▼
ProviderFactory.create(config)            SecretResolver.resolve(ref)
     │                                    → reads os.environ[secret_key]
     ▼                                    → returns plaintext key
ProviderRegistry.get(provider_type)
     │
     ▼
AIProvider instance
(OpenAIProvider / AnthropicProvider)
     │
     ├── verify_auth()
     │       │
     │       ├── _resolve_key()  ──────► SecretResolver
     │       ├── CredentialValidator.validate_*_key(key)
     │       └── ProviderHttpClient.get("/v1/models")
     │
     ├── check_connection()
     │       └── calls verify_auth(), updates _healthy state
     │
     └── list_models()
             └── ProviderHttpClient.get("/v1/models")
                     └── enriches response with _MODEL_ENRICHMENT
```

### AIProvider (interface.py)

The abstract base class establishes the contract for all adapters. Inherits from `HealthCheckInterface`, which provides:
- `check_connection() → ConnectionStatus`
- `verify_auth() → bool`
- `check_capability(capability: str) → bool`
- `is_healthy` property

Additional abstract methods in `AIProvider`:
- `provider_type → ProviderType`
- `capabilities → ProviderCapabilities`
- `list_models() → list[ModelMetadata]`
- `complete(request) → ProviderResponse`
- `get_usage(start, end) → list[UsageData]`

### ProviderFactory / ProviderRegistry

`ProviderRegistry` maps `ProviderType → type[AIProvider]`. It's populated by `ProviderFactory.build_default_registry()`. The factory validates after instantiation that the adapter's self-reported `provider_type` matches the key it was registered under — catching registry misconfiguration at startup rather than at runtime.

### SecretResolver

Reads from `os.environ`. Never logs the resolved value. Raises `AuthenticationError` (not `ValueError`) so callers always get a typed error through the ProviderError hierarchy.

### CredentialValidator

Validates key format before any network call. Checks prefix and minimum length only. Does NOT validate the key against the provider — that's done by `verify_auth()`. Key value is never included in error messages.

### ProviderInfo (info.py)

A frozen Pydantic model that flattens `ProviderCapabilities` dataclass fields. The flattening is necessary because Pydantic v2 doesn't serialize frozen dataclasses cleanly when nested inside a `BaseModel`. The `from_capabilities()` classmethod handles the translation.

### ProviderCapabilities (capabilities.py)

A frozen dataclass with boolean flags and numeric fields describing what a provider can do. It is module-level (`_CAPABILITIES` constant), not per-instance — capabilities are the same for all instances of a given provider type.

### ProviderConfig (config.py)

The config hierarchy:
```
ProviderConfig
├── api_key_ref: SecretReference | None
├── base_url: str | None  (SSRF-validated at construction)
├── timeout_seconds: float
└── extra: dict[str, Any]  (cannot contain credential keys)

OpenAIConfig(ProviderConfig)
├── organization_id: str | None
└── project_id: str | None

AnthropicConfig(ProviderConfig)
└── anthropic_version: str = "2023-06-01"
```

---

## 4. OpenAI Adapter

### Authentication

OpenAI uses bearer token authentication:

```
Authorization: Bearer sk-proj-xxxxxxxxxxxx
```

Built by `BearerTokenAuth(key)`. The key is resolved from the environment just before each request and held only for the duration of that request.

### Health & Connection Testing

The `check_connection()` method wraps `verify_auth()` in a `try/except Exception` that catches ALL exceptions. On success: sets `_healthy = True`, records timestamp, returns `ConnectionStatus(is_connected=True, health_status=HEALTHY)`. On any failure: sets `_healthy = False`, records the exception message in `ConnectionStatus.error_message`, returns `ConnectionStatus(is_connected=False, health_status=UNHEALTHY)`.

This means `check_connection()` **never raises** — it always returns a status. This is the correct behaviour for a health check.

### Model Discovery

`list_models()` calls `GET /v1/models` and receives a JSON body:

```json
{
  "data": [
    {"id": "gpt-4o", ...},
    {"id": "gpt-4o-mini", ...},
    ...
  ]
}
```

Each model ID is passed to `_enrich_model()`, which looks up the ID in `_MODEL_ENRICHMENT`. Known models get display names, context window sizes, and capability flags. Unknown models from the API (newly added by OpenAI) get the ID as the display name and no capability flags — they appear in the list but without enriched metadata.

The static enrichment covers: `gpt-4o`, `gpt-4o-mini`, `gpt-4-turbo`, `gpt-3.5-turbo`.

### Capabilities

`check_capability("streaming")` looks up `_CAPABILITIES.supports_streaming`. No network call. Returns `bool`. Unknown capability names return `False`.

### Error Handling

All HTTP errors are normalised by `map_http_error()`:
- 401 → `AuthenticationError` (not retryable)
- 403 → `AuthenticationError` (not retryable)
- 429 → `RateLimitError` (retryable, parses `Retry-After` header)
- 500/502/503 → `InternalProviderError` (retryable)
- Network failures → `NetworkError` (retryable)

### Future Usage Collection (EP-08)

`get_usage()` raises `NotImplementedError` until EP-08. EP-08 will call `GET /v1/usage` with date range parameters.

---

## 5. Anthropic Adapter

### Authentication

Anthropic requires two headers on every request:

```
x-api-key: sk-ant-xxxxxxxxxxxx
anthropic-version: 2023-06-01
```

This is implemented as `CompositeAuth(ApiKeyHeaderAuth("x-api-key", key), ApiKeyHeaderAuth("anthropic-version", version))`. The version header is not a credential — it selects the API version — but it's treated as a header just like the key for simplicity.

### Version Header

The `anthropic_version` field on `AnthropicConfig` defaults to `"2023-06-01"` but can be overridden per config. `_get_api_version()` reads it from the config if the config is an `AnthropicConfig` instance, falling back to the module constant.

### Health & Model Discovery

Identical pattern to OpenAI. `check_connection()` calls `verify_auth()` and caches the result. `list_models()` calls `GET /v1/models` — note this is a beta endpoint for Anthropic and requires a valid key.

Static enrichment covers: `claude-3-5-sonnet-20241022`, `claude-3-5-haiku-20241022`, `claude-3-opus-20240229`. Anthropic models include `max_output_tokens` in enrichment, which OpenAI models don't (OpenAI doesn't expose this in the models list).

### Future Usage Collection (EP-08)

`get_usage()` raises `NotImplementedError`. Anthropic's usage API differs from OpenAI's — EP-08 will address both.

---

## 6. Credential Validation

### API Key Validation

`CredentialValidator` is a stateless class (no instance state) with two class methods:

```
validate_openai_key(key: str) → None
  - Prefix: must start with "sk-proj-" or "sk-"
  - Length: must be >= 20 characters
  - Raises: InvalidRequestError (message never contains the key value)

validate_anthropic_key(key: str) → None
  - Prefix: must start with "sk-ant-"
  - Length: must be >= 20 characters
  - Raises: InvalidRequestError
```

Validation runs before any network call. If a key is obviously wrong (wrong prefix), we fail immediately without incurring a network round trip or leaking timing information about key validity.

### SecretReference

```python
class SecretReference(BaseModel):
    secret_store: SecretStoreType = SecretStoreType.ENV
    secret_key: str   # e.g., "OPENAI_API_KEY"
```

`SecretReference` stores the *name* of the secret (the env var name), never the secret itself. Its `__repr__` redacts `secret_key` to `<redacted>`, so even if a `SecretReference` appears in logs, the env var name does not appear.

### Why Secrets Never Appear in Logs

The data flow for credential handling:

```
SecretReference(secret_key="OPENAI_API_KEY")
         │
         ▼
SecretResolver.resolve(ref)
  → value = os.environ["OPENAI_API_KEY"]
  → value is a local variable, never assigned to any attribute
         │
         ▼  (passed directly to auth strategy)
BearerTokenAuth(value)
  → self._token = value  (private, not in __repr__)
         │
         ▼  (called once per request)
auth.headers()
  → returns {"Authorization": "Bearer sk-..."}
         │
         ▼  (merged into headers dict)
ProviderHttpClient._request()
  → headers dict sent to httpx
  → headers dict NEVER passed to RequestTelemetry
  → headers dict NEVER included in any log event
  → headers dict NEVER included in any exception message
```

The key travels through memory as a local variable / private attribute and reaches only the HTTP wire.

---

## 7. Provider Lifecycle

### Full Lifecycle Diagram

```
User action: "Test my OpenAI connection"
         │
         ▼
POST /v1/providers/openai/test
         │
         ▼
providers.py: _get_openai_provider()
  → reads OPENAI_API_KEY env var name from SecretReference
  → constructs OpenAIConfig (no key yet)
  → constructs OpenAIProvider(config)
         │
         ▼
adapter.check_connection()
         │
         ├─► adapter.verify_auth()
         │         │
         │         ├─► _resolve_key()
         │         │         └─► SecretResolver.resolve(ref)
         │         │               → os.environ["OPENAI_API_KEY"] → key
         │         │
         │         ├─► CredentialValidator.validate_openai_key(key)
         │         │         → checks prefix, length
         │         │         → raises InvalidRequestError if bad
         │         │
         │         └─► _build_client(key) → ProviderHttpClient
         │                   └─► GET /v1/models
         │                         → 200 OK: return True
         │                         → 401:    raise AuthenticationError
         │                         → 429:    raise RateLimitError
         │                         → 5xx:    raise InternalProviderError
         │                         → network: raise NetworkError
         │
         ├─► On success:
         │       _healthy = True
         │       _last_checked = datetime.now(UTC)
         │       → ConnectionStatus(is_connected=True, HEALTHY)
         │
         └─► On any exception:
                 _healthy = False
                 _last_checked = datetime.now(UTC)
                 → ConnectionStatus(is_connected=False, UNHEALTHY,
                                    error_message=str(exc))
         │
         ▼
TestConnectionResponse(
    provider="openai",
    status=ConnectionStatus(...),
    auth_valid=True/False
)
         │
         ▼
HTTP 200 response to user

─────────────────────────────────────────────

Future lifecycle (EP-08): Usage Collection

Scheduler fires: "Collect OpenAI usage for yesterday"
         │
         ▼
adapter.get_usage(start=yesterday, end=today)
  → _resolve_key() → key
  → GET /v1/usage?date=yesterday
  → parse response → list[UsageData]
  → write to ClickHouse
```

---

## 8. Error Handling

### HTTP Error Normalisation

`map_http_error()` in `app/http/client.py` converts HTTP status codes to typed exceptions:

```
HTTP 401  → AuthenticationError("Invalid API key or unauthorized")       retryable=False
HTTP 403  → AuthenticationError("Access forbidden ...")                  retryable=False
HTTP 404  → InvalidRequestError("Endpoint not found: <url>")             retryable=False
HTTP 408  → NetworkError("Request timed out")                            retryable=True
HTTP 429  → RateLimitError("Rate limit exceeded", retry_after_seconds=N) retryable=True
HTTP 500  → InternalProviderError("Provider server error (500)")         retryable=True
HTTP 502  → InternalProviderError("Provider server error (502)")         retryable=True
HTTP 503  → InternalProviderError("Provider server error (503)")         retryable=True
HTTP 504  → NetworkError("Request timed out")                            retryable=True
other     → ProviderError("Unexpected HTTP <N>")                         retryable=False
```

### Transport Error Normalisation

```
httpx.TimeoutException    → NetworkError("Request timed out")
httpx.ConnectError        → NetworkError("Connection failed — DNS or connection refused")
httpx.RemoteProtocolError → NetworkError("Protocol error from provider: ...")
httpx.HTTPError           → NetworkError("HTTP transport error: ...")
```

### Authentication Errors

`check_connection()` catches ALL exceptions (including `AuthenticationError`) and returns `ConnectionStatus(is_connected=False, error_message=...)`. This means the `/test` endpoint always returns HTTP 200 — the error is in the response body.

`list_models()` does NOT catch exceptions — `AuthenticationError`, `RateLimitError`, etc. propagate to the endpoint handler, which converts them to `HTTPException(401)` or `HTTPException(502)`.

### Rate Limits

`RateLimitError` carries `retry_after_seconds: float | None`, parsed from the `Retry-After` response header. EP-08's scheduler should inspect this value when planning the next collection attempt.

### Retry Strategy

`ExponentialRetryPolicy.should_retry(attempt, error)` returns `True` when:
1. `attempt < max_attempts`
2. `error.retryable is True`

Callers (EP-08 collection service) are expected to implement the retry loop using `ExponentialRetryPolicy.get_delay(attempt)` to compute sleep duration.

---

## 9. Testing Strategy

### Mock Transport Injection

Tests never make real network calls. Instead, tests inject `httpx.MockTransport` as the `http_transport` parameter to adapter constructors:

```python
transport = httpx.MockTransport(handler=lambda req: httpx.Response(200, json={"data": []}))
provider = OpenAIProvider(config, http_transport=transport)
```

`httpx.MockTransport` is part of httpx's public API — it's stable and supported for exactly this use case.

### Hermetic Testing

Every test is self-contained:
- No `pytest.monkeypatch` for HTTP calls
- Environment variables monkeypatched only for `os.environ` reads in `SecretResolver`
- No live network calls, no live provider APIs
- No shared mutable state between tests

### Test Structure

```
TestBearerTokenAuth         — auth strategy unit tests
TestApiKeyHeaderAuth        — auth strategy unit tests
TestCompositeAuth           — composite merge tests
TestMapHttpError            — error mapping for all status codes
TestProviderHttpClient      — integration of client + transport
TestRequestTelemetry        — latency measurement, error capture
TestExponentialRetryPolicy  — all 4 backoff strategies
TestSecretResolver          — env var resolution and error cases
TestCredentialValidatorOpenAI    — prefix/length validation
TestCredentialValidatorAnthropic — prefix/length validation
TestProviderInfo            — model construction, frozen fields
TestOpenAIProvider          — all public methods, error paths
TestAnthropicProvider       — all public methods, error paths
TestHttpxTransport          — basic request + aclose
TestProvidersAPI            — ASGI endpoint tests (no network)
```

### Coverage

- All error mapping cases are tested (401, 403, 404, 408, 429, 500, 502, 503, 504, 418)
- Auth error non-retryability tested
- Rate limit retryability tested
- Key value absence from error messages tested
- Connection state transitions (healthy → unhealthy → healthy) tested
- Static model enrichment tested
- Unknown model ID fallback tested
- API endpoints tested against ASGI app (no network)

### Why HTTP Calls Are Mocked

1. Tests run without provider credentials in CI
2. Tests are deterministic — no flakiness from provider API availability
3. Tests cover error cases that can't be reliably triggered against live APIs (429, 503)
4. Tests run in milliseconds, not seconds

---

## 10. Top 30 Engineering Concepts Learned

1. **Transport abstraction** — separating the HTTP transport ABC from the client that uses it makes the entire HTTP layer swap-friendly without monkey-patching
2. **Strategy pattern for auth** — `HttpAuth` subclasses encapsulate auth logic; the client knows nothing about how auth headers are built
3. **Composite auth** — merging multiple auth strategies via `CompositeAuth` enables Anthropic's two-header auth without special-casing the client
4. **Injectable mock transport** — `httpx.MockTransport` as a constructor parameter enables hermetic tests without patching
5. **`async with` for resource lifecycle** — `ProviderHttpClient` is an async context manager ensuring `aclose()` is always called even on exception
6. **Frozen dataclass for capabilities** — `ProviderCapabilities` is `frozen=True, slots=True` making it immutable, hashable, and memory-efficient
7. **Pydantic frozen model** — `ProviderInfo(model_config={"frozen": True})` makes response models immutable after construction
8. **Discriminated unions** — `MessageContent` uses `Literal["type"]` discriminator for fast, unambiguous Pydantic dispatch
9. **SecretStr in Settings** — `SecretStr` fields prevent values appearing in `repr`, `str`, or log output even if the Settings object is inadvertently serialised
10. **SecretReference pattern** — storing the *name* of a secret rather than the secret itself means credentials never appear in config files, databases, or logs
11. **StrEnum for typed strings** — `BackoffStrategy`, `HealthStatus`, `SecretStoreType` as `StrEnum` means string serialisation is automatic and comparisons work without `.value`
12. **Error retryability as a field** — `ProviderError.retryable: bool` encodes retry behaviour at the error class level, eliminating conditional logic at the retry site
13. **Monotonic clock for latency** — `time.monotonic()` rather than `datetime.now()` for latency measurement avoids clock adjustment errors
14. **Deferred imports for circular avoidance** — `from app.providers.config import AnthropicConfig` inside `_get_api_version()` breaks circular imports while keeping the top-level imports clean
15. **Module-level constants for capabilities** — `_CAPABILITIES` and `_MODEL_ENRICHMENT` as module-level constants avoid reconstructing them per instance
16. **Static enrichment + live API IDs** — splitting model discovery into live IDs (from API) + static metadata (from code) is resilient to new model additions without code changes
17. **`getattr` for capability lookup** — `getattr(_CAPABILITIES, f"supports_{cap}", False)` avoids a large if/elif chain for capability checking
18. **Telemetry as a sync context manager** — `RequestTelemetry` is `__enter__`/`__exit__` (synchronous) used inside async code — this works because the timing calls are synchronous
19. **`_make_response` with attached request** — httpx responses need an attached request for `response.url` to work; tests must set `resp.request = httpx.Request(...)` explicitly
20. **`_mock_transport` yields responses in order** — using `iter()` to yield successive responses allows tests to simulate multi-step flows
21. **Catch-all in `check_connection()`** — `except Exception` in health checks is correct because health probes must not propagate exceptions to callers
22. **`ConnectionStatus` is immutable** — frozen Pydantic model prevents accidental mutation of health state after it's constructed
23. **`_last_checked` vs `checked_at`** — the adapter stores `_last_checked: datetime` internally; `ConnectionStatus.checked_at` exposes it per-check, not as a mutable global
24. **`ProviderFactory` post-construction validation** — validating `instance.provider_type == registry_key` after creation catches registry misconfigurations eagerly
25. **`SecretReference.__repr__` redaction** — overriding `__repr__` to return `<redacted>` means logging a config object never leaks the env var name
26. **`_SUPPORTED_PROVIDERS` as explicit set** — the API layer maintains an explicit whitelist of supported providers rather than forwarding all requests to the registry
27. **`get_provider_info()` returns static data** — the `/info` endpoint never makes a network call; it reflects the last-known health state
28. **`asyncio_mode = "auto"` in pytest** — avoids the need to mark every async test with `@pytest.mark.asyncio` explicitly
29. **`frozen=True` on `ProviderConfig` via `model_config`** — using `{"frozen": True}` in Pydantic v2 rather than the v1 `class Config` syntax
30. **`fail_under = 70` in coverage config** — the test suite enforces minimum branch coverage; dropping below 70% fails the CI run
