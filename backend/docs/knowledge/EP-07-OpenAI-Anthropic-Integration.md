# EP-07: OpenAI & Anthropic Provider Integration — Knowledge Transfer

## What was built

EP-07 implements the first production-ready AI provider integrations (OpenAI and Anthropic) along with a shared HTTP transport layer used by all future provider adapters.

## File map

| File | Feature | Description |
|------|---------|-------------|
| `app/http/__init__.py` | F-033 | Public exports for the HTTP layer |
| `app/http/transport.py` | F-033 | `HttpTransport` ABC + `HttpxTransport` (wraps httpx) |
| `app/http/auth.py` | F-033 | `BearerTokenAuth`, `ApiKeyHeaderAuth`, `CompositeAuth` |
| `app/http/client.py` | F-033, F-039 | `ProviderHttpClient`, `map_http_error()` |
| `app/http/telemetry.py` | F-033 | `RequestTelemetry` — latency logging, never logs secrets |
| `app/http/retry.py` | F-033 | `ExponentialRetryPolicy` (implements EP-06 `RetryPolicy` ABC) |
| `app/providers/credential.py` | F-036 | `SecretResolver` + `CredentialValidator` |
| `app/providers/info.py` | F-040 | `ProviderInfo` Pydantic model |
| `app/providers/adapters/openai.py` | F-034 | Full OpenAI adapter |
| `app/providers/adapters/anthropic.py` | F-035 | Full Anthropic adapter |
| `app/schemas/providers.py` | — | `TestConnectionResponse`, `ModelsResponse` |
| `app/api/v1/providers.py` | — | REST endpoint handlers |
| `app/config/settings.py` | — | Added `openai_api_key`, `anthropic_api_key` optional fields |

## Authentication

**OpenAI**: `Authorization: Bearer <api_key>` via `BearerTokenAuth`

**Anthropic**: `x-api-key: <api_key>` + `anthropic-version: 2023-06-01` via `CompositeAuth`

Keys are read from environment variables via `SecretResolver`. The env var name is stored in `ProviderConfig.api_key_ref.secret_key`; the key value is resolved at request time and never stored.

## Mock injection for tests

```python
from app.providers.adapters.openai import OpenAIProvider
from app.providers.config import OpenAIConfig, SecretReference, SecretStoreType

config = OpenAIConfig(
    provider_type="openai",
    display_name="OpenAI",
    api_key_ref=SecretReference(secret_store=SecretStoreType.ENV, secret_key="OPENAI_API_KEY"),
)
transport = httpx.MockTransport(handler=my_handler)
provider = OpenAIProvider(config, http_transport=transport)
```

The `http_transport` keyword argument is injected into `ProviderHttpClient`, bypassing real network calls.

## Health state lifecycle

1. `provider.is_healthy` → `False` on creation
2. `await provider.check_connection()` → makes live API call, caches result in `_healthy`
3. `provider.is_healthy` → reflects result of last `check_connection()` call
4. `ConnectionStatus.health_status` → `HEALTHY` on success, `UNHEALTHY` on any exception

## Model enrichment

`list_models()` fetches model IDs from the live API, then enriches known IDs with static metadata (display name, context window, capabilities). Unknown model IDs returned by the API are included with minimal metadata (id as display name, no context window).

## Error mapping

HTTP status codes are mapped to typed `ProviderError` subclasses in `map_http_error()`:

| HTTP | Error class | Retryable |
|------|-------------|-----------|
| 401, 403 | `AuthenticationError` | No |
| 404 | `InvalidRequestError` | No |
| 408, 504 | `NetworkError` | Yes |
| 429 | `RateLimitError` | Yes |
| 500, 502, 503 | `InternalProviderError` | Yes |

## Security invariants

- Key values are **never** in error messages, log lines, or stack traces
- `CredentialValidator` checks format before any network call
- `RequestTelemetry` receives only method, URL, provider type — no auth headers
- `SecretResolver` raises `AuthenticationError` (not `ValueError`) so callers always get a typed error

## What EP-07 does NOT implement

- `complete()` / `stream()` — deferred to a later EP
- Usage collection (`get_usage()`) — deferred to EP-08
- Background workers, polling, WebSocket streaming
- Vault / AWS Secrets Manager secret stores — reserved for EP-09+
