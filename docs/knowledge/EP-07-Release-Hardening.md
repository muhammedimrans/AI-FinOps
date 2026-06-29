# EP-07 Release Hardening — Knowledge Transfer

**Sprint:** EP-07.5 Production Hardening  
**Date:** 2026-06-29  
**Status:** Complete — Ready for EP-08  
**Test result:** 688 passed, 30 skipped, 0 failed

---

## Context

EP-07 implemented the OpenAI and Anthropic provider adapters together with the
full HTTP transport layer. The combined architecture review and production
readiness review returned **APPROVED WITH MINOR CHANGES** with six findings.
This sprint resolves all six before EP-08 (usage collection) begins.

---

## PH-01: Shared HTTP Client

**Finding:** A new `httpx.AsyncClient` was created for every provider call,
bypassing connection pool reuse.

**Fix:** `HttpxTransport` is instantiated once per adapter in `__init__` and
stored as `self._transport`. `ProviderHttpClient` gains a
`transport: HttpxTransport | None` constructor parameter.

- When `transport` is provided: `_owns_transport = False`; `aclose()` is a no-op.
- When `transport` is omitted: the client creates and owns its own transport.

The existing `async with self._build_client(key) as client:` pattern in the
adapters continues to work safely — opening and closing the client context is
now a no-op at the HTTP level because the transport is owned by the adapter.

Both `OpenAIProvider` and `AnthropicProvider` expose:

```python
async def aclose(self) -> None: ...
async def __aenter__(self) -> Self: ...
async def __aexit__(self, *args) -> None: ...
```

---

## PH-02: Retry Integration

**Finding:** `ProviderHttpClient` had no retry logic; every transient failure
surfaced immediately to the caller.

**Fix:** `ProviderHttpClient._request()` implements a `while True` retry loop:

```
attempt = 0
while True:
    attempt += 1
    try:
        response = await transport.request(...)
    except httpx.TimeoutException → NetworkError
        if retryable: sleep(delay); continue
        raise
    ...
    if not response.is_success:
        err = map_http_error(response)
        if retryable: sleep(delay); continue
        raise err
    return response.json()
```

**`ExponentialRetryPolicy`** implements `RetryPolicy`:

| Error type | `retryable` | Action |
|---|---|---|
| `AuthenticationError` | `False` | Raise immediately |
| `InvalidRequestError` | `False` | Raise immediately |
| `QuotaExceededError` | `False` | Raise immediately |
| `RateLimitError` | `True` | Retry; honour `Retry-After` header |
| `NetworkError` | `True` | Retry with exponential backoff |
| `InternalProviderError` | `True` | Retry with exponential backoff |

Default config: `max_attempts=3`, `initial_delay_seconds=1.0`,
`backoff_multiplier=2.0`, `max_delay_seconds=60.0`.

**Testing pattern** — disable retries in single-attempt tests to avoid
`StopIteration` / slow sleeps:

```python
def _no_retry_policy() -> ExponentialRetryPolicy:
    return ExponentialRetryPolicy(RetryConfig(max_attempts=1))

async with ProviderHttpClient(..., retry_policy=_no_retry_policy()) as client:
    ...
```

---

## PH-03: Factory Enforcement

**Finding:** Some code paths instantiated adapter classes directly instead of
going through `ProviderFactory`.

**Fix:** `app/api/v1/providers.py` creates all adapters exclusively via:

```python
def _get_adapter(pt: ProviderType, *, with_key: bool) -> AIProvider:
    config = _make_config_with_key(pt) if with_key else _make_config_no_key(pt)
    return ProviderFactory(get_registry()).create(config)
```

`ProviderFactory.create()` applies the EP-06.5 `provider_type` cross-check:
if the config's `provider_type` does not match the registered adapter class,
`ProviderConfigurationError` is raised at creation time.

---

## PH-04: AIProvider Interface Completion

**Finding:** `get_provider_info()` was implemented in the two live adapters but
not declared in the `AIProvider` ABC, so stubs could silently omit it.

**Fix:** `get_provider_info()` added as an `@abstractmethod` to `AIProvider`:

```python
@abstractmethod
def get_provider_info(self, health: HealthStatus | None = None) -> ProviderInfo:
    ...
```

All seven adapter stubs implement it via `ProviderInfo.from_capabilities()`.

---

## PH-05: Provider Enumeration

**Finding:** The supported-provider gate in `providers.py` used a raw string set
with no compile-time link to `ProviderType`.

**Fix:** Replaced with a typed frozenset of enum members:

```python
_PRODUCTION_PROVIDERS: frozenset[ProviderType] = frozenset({
    ProviderType.OPENAI,
    ProviderType.ANTHROPIC,
})
```

`_require_supported()` validates in two steps:
1. `ProviderType(provider)` — raises `ValueError` → HTTP 404 for unknown strings
2. `pt not in _PRODUCTION_PROVIDERS` — HTTP 404 for known but non-production types

This means `grok`, `azure_openai`, `ollama`, `openrouter`, and `google` all
return HTTP 404 until their adapters are promoted to production.

---

## PH-06: HTTP Status Consistency

**Finding:** `POST /providers/{provider}/test` caught all exceptions and returned
HTTP 200 with `auth_valid=false` even for authentication failures.

**Fix:** The endpoint calls `adapter.verify_auth()` directly and propagates
exceptions through standard FastAPI exception handlers:

```python
try:
    await adapter.verify_auth()
    return TestConnectionResponse(..., auth_valid=True)
except (AuthenticationError, InvalidRequestError) as exc:
    raise HTTPException(status_code=401, detail=str(exc)) from exc
except ProviderError as exc:
    raise HTTPException(status_code=502, detail=str(exc)) from exc
```

HTTP status semantics:
- Missing/invalid API key → **HTTP 401**
- Provider network/server error → **HTTP 502**
- Successful auth → **HTTP 200** with `auth_valid=true`

---

## PH-07: Transport Improvements

**Finding:** Missing request IDs, user agent, structured logging, and unclear
transport ownership.

**Fixes applied:**

- `X-Request-ID: <uuid4>` added to every outbound request header
- `User-Agent: ai-finops/<provider_type>` added
- `ProviderHttpClient.post()` convenience method added for EP-08 readiness
- `aclose()` ownership chain is explicit (`_owns_transport` flag)
- All logging uses `structlog.get_logger(__name__)` — no `print()` calls

---

## Test Coverage Added

| Class | PH item | What it verifies |
|---|---|---|
| `TestSharedTransport` | PH-01 | Transport created on init; adapter aclose; context manager; `_owns_transport` flag |
| `TestProviderHttpClientRetry` | PH-02 | Retry on 503 → success; exhaust budget; no retry on 401/404; retry-after header |
| `TestFactoryEnforcement` | PH-03 | Factory creates correct adapter; type mismatch raises `ProviderConfigurationError` |
| `TestProvidersAPIHardened` | PH-05/06 | grok/azure_openai return 404; missing key returns 401 |

---

## Ready for EP-08

All six production findings are closed. The HTTP transport layer is stable:

- Connection pooling: one `HttpxTransport` per adapter lifetime
- Retry: exponential backoff with `Retry-After` support
- Error mapping: deterministic HTTP status → `ProviderError` subclass
- Factory: all adapters created via registry, type-checked at creation
- API: correct HTTP status codes for auth failures and network errors
- Observability: structured logs, request IDs, user-agent on every request

EP-08 may use `ProviderHttpClient` with `post()` for usage collection API calls.
