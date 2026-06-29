# Provider Integration Architecture

## Overview

AI FinOps uses a layered provider abstraction to support multiple AI providers (OpenAI, Anthropic, and others) through a unified interface. EP-07 implements the first production-ready adapters.

## Layer diagram

```
┌─────────────────────────────────────────┐
│         REST API  (FastAPI)             │
│  POST /v1/providers/{p}/test            │
│  GET  /v1/providers/{p}/models          │
│  GET  /v1/providers/{p}/info            │
└──────────────────┬──────────────────────┘
                   │
┌──────────────────▼──────────────────────┐
│         Provider Adapters               │
│  OpenAIProvider  |  AnthropicProvider   │
│  (implements AIProvider ABC)            │
└──────────────────┬──────────────────────┘
                   │
┌──────────────────▼──────────────────────┐
│         ProviderHttpClient              │
│  • Injects X-Request-ID + User-Agent    │
│  • Attaches HttpAuth headers            │
│  • Calls RequestTelemetry               │
│  • Maps HTTP errors → ProviderError     │
└──────────────────┬──────────────────────┘
                   │
┌──────────────────▼──────────────────────┐
│         HttpxTransport                  │
│  • Wraps httpx.AsyncClient              │
│  • Injectable mock_transport for tests  │
└─────────────────────────────────────────┘
```

## Key design decisions

### Mock injection
Adapters accept `http_transport: httpx.AsyncBaseTransport | None = None` as a keyword-only constructor argument. When set, it is passed to `ProviderHttpClient`, bypassing real network calls. This makes tests fully hermetic without patching.

### Credential handling
Credentials are resolved from environment variables at request time by `SecretResolver`. The resolved value lives only in memory for the duration of a single request. It is never:
- Written to logs
- Included in error messages
- Stored in config files
- Passed to telemetry

### Health state
Adapters maintain `_healthy: bool` (initially `False`). Each `check_connection()` call updates this state. `is_healthy` returns the cached value. There is no background poller — health is checked on demand.

### Static enrichment
`list_models()` fetches live model IDs from the provider API, then enriches known IDs with static metadata (context window, capability flags). Unknown IDs from the API are included with minimal fallback metadata. This approach is resilient to new models being added by providers.

## Error hierarchy

```
ProviderError
├── AuthenticationError (not retryable)
├── InvalidRequestError (not retryable)
├── QuotaExceededError (not retryable)
├── NetworkError (retryable)
├── RateLimitError (retryable, has retry_after_seconds)
├── InternalProviderError (retryable)
└── ProviderConfigurationError (not retryable, config-time)
```

## Adding a new provider

1. Create `app/providers/adapters/{name}.py` implementing `AIProvider`
2. Accept `http_transport: httpx.AsyncBaseTransport | None = None` in `__init__`
3. Define `_CAPABILITIES = ProviderCapabilities(...)` and `_MODEL_ENRICHMENT = {...}`
4. Implement: `provider_type`, `capabilities`, `is_healthy`, `verify_auth`, `check_connection`, `list_models`, `check_capability`, `get_provider_info`
5. Register in `ProviderFactory.build_default_registry()`
6. Add to `_SUPPORTED_PROVIDERS` in `app/api/v1/providers.py` and add factory helpers
7. Add tests in `tests/test_ep07.py` or a new `test_ep{N}.py`
