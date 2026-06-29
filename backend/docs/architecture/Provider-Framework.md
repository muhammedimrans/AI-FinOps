# Provider Framework Architecture

## Overview

The provider framework (`app/providers/`) is an abstraction layer that decouples the rest of the application from any specific AI provider SDK. It defines shared interfaces, typed configuration, a registry/factory, and stub adapters for each supported provider.

## Layer diagram

```
┌────────────────────────────────────────────────────────┐
│  Application code (services, API routes)               │
└────────────────────────┬───────────────────────────────┘
                         │ uses
                         ▼
┌────────────────────────────────────────────────────────┐
│  ProviderFactory  ←→  ProviderRegistry                 │
│  create(config) → AIProvider                           │
└────────────────────────┬───────────────────────────────┘
                         │ instantiates
                         ▼
┌────────────────────────────────────────────────────────┐
│  AIProvider (ABC)                                      │
│  check_connection() / list_models() / complete() / ... │
└────────────────────────┬───────────────────────────────┘
                         │ implemented by
              ┌──────────┴──────────────┐
    ┌─────────▼──────┐       ┌──────────▼────────┐
    │ OpenAIProvider │  ...  │ OllamaProvider    │
    └────────────────┘       └───────────────────┘
```

## Key types

### `AIProvider` (abstract)

Defined in `app/providers/interface.py`. Every adapter must implement:

- `provider_type` → `ProviderType`
- `capabilities` → `ProviderCapabilities`
- `check_connection()` → `ConnectionStatus`
- `list_models()` → `list[ModelMetadata]`
- `complete(request)` → `ProviderResponse`
- `verify_auth()` → `bool`

### `ProviderCapabilities`

Frozen dataclass capturing what a provider supports (streaming, vision, tool calling, fine-tuning, etc.) and its limits (max context window, supported model IDs). Defined at module level in each adapter as a constant.

### `ProviderConfig` hierarchy

Each provider has a typed config class. `ProviderConfig` validates that `extra` fields do not contain plaintext credentials. Credentials are always represented as `SecretReference` pointing to an external secrets store.

### `ProviderRegistry`

Maps `ProviderType` → `type[AIProvider]`. The module-level `get_registry()` returns a lazily-built singleton populated by `ProviderFactory.build_default_registry()`.

### `ProviderFactory`

Takes a `ProviderRegistry` and a `ProviderConfig`, resolves the `ProviderType`, looks up the class, and instantiates it.

### Error hierarchy

All errors derive from `ProviderError(Exception)`. The `retryable` flag allows generic retry logic to decide whether to attempt again without knowing the concrete type.

```
ProviderError
├── RateLimitError        (retryable=True, has retry_after_seconds)
├── NetworkError          (retryable=True)
├── InternalProviderError (retryable=True)
├── AuthenticationError   (retryable=False)
├── QuotaExceededError    (retryable=False)
└── InvalidRequestError   (retryable=False)
```

### Retry interfaces

`RetryPolicy` and `CircuitBreaker` ABCs are defined in `app/providers/retry.py`. Concrete implementations are deferred to EP-07.

## Supported providers

| ProviderType    | Adapter class          | Notes                              |
|-----------------|------------------------|------------------------------------|
| `openai`        | `OpenAIProvider`       | GPT-4o, GPT-4 Turbo, GPT-3.5      |
| `anthropic`     | `AnthropicProvider`    | Claude 3.5 Sonnet/Haiku, Opus      |
| `grok`          | `GrokProvider`         | Grok 2, Grok 2 Vision              |
| `google`        | `GoogleProvider`       | Gemini 1.5 Pro/Flash, 2.0 Flash    |
| `azure_openai`  | `AzureOpenAIProvider`  | Azure-hosted GPT models            |
| `openrouter`    | `OpenRouterProvider`   | Multi-provider routing gateway     |
| `ollama`        | `OllamaProvider`       | Self-hosted; no API key required   |

## What is NOT in this layer

- Real HTTP calls to provider APIs (EP-07)
- Token counting or cost calculation (EP-08)
- Usage data collection or storage (EP-08)
- Rate-limit enforcement (EP-07)
- Circuit-breaker state machine (EP-07)
